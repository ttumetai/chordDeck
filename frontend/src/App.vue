<script setup>
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import UploadZone from './components/UploadZone.vue'
import AnalyzeConfirm from './components/AnalyzeConfirm.vue'
import ChordTimeline from './components/ChordTimeline.vue'
import ExportMenu from './components/ExportMenu.vue'
import HistoryList from './components/HistoryList.vue'
import EditWorkspace from './components/EditWorkspace.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import { bus } from './lib/events.js'

const state = ref('idle') // idle | analyzing | ready | error
const errorMsg = ref('')
const result = shallowRef(null)
const selectedFile = ref(null)
const uploadZoneRef = ref(null)
const uploadConfirmOpen = ref(false)
const uploadBusy = ref(false)
const uploadCache = shallowRef(null)
const reanalyzeConfirmItem = shallowRef(null)
const engineCapabilities = ref({})
const preferredEngine = ref('auto')
const history = ref([])
const analyzingKind = ref('analyze') // analyze | history | reanalyze
const reanalyzingId = ref('')
const analysisProgress = ref(0)
const analysisStage = ref('queued')
let pollToken = 0

// 编辑工作台
const editOpen = ref(false)
// 覆盖人工修改前的确认：{ title, message, confirmText, run }
const confirmRef = ref(null)
watch([confirmRef, uploadConfirmOpen, reanalyzeConfirmItem], ([v, uploadOpen, reanalyzeOpen]) => {
  if (v || uploadOpen || reanalyzeOpen) document.body.classList.add('modal-open')
  else document.body.classList.remove('modal-open')
})

async function fetchHistory() {
  try {
    const resp = await fetch('/api/history')
    if (resp.ok) history.value = await resp.json()
  } catch {
    /* 历史记录加载失败不阻塞主流程 */
  }
}

async function fetchEngineCapabilities() {
  try {
    const resp = await fetch('/api/engines')
    if (resp.ok) {
      const data = await resp.json()
      engineCapabilities.value = data
      preferredEngine.value = data.recommended || 'auto'
    }
  } catch {
    /* 检测接口不可用时保留自动模式；后端仍会校验引擎 */
  }
}

onMounted(() => {
  fetchHistory()
  fetchEngineCapabilities()
})

/* BPM 徽标回填：旧记录无 bpm 时静默拉取（GET beats 会按需计算） */
async function backfillBpm(analysis) {
  if (!analysis || analysis.bpm != null) return
  try {
    const resp = await fetch(`/api/analyses/${analysis.id}/beats`)
    if (resp.ok) {
      const data = await resp.json()
      if (data.bpm != null) result.value = { ...analysis, bpm: data.bpm, beats_count: data.beats?.length || 0 }
    }
  } catch {
    /* 静默失败 */
  }
}

function applyResult(data) {
  analysisProgress.value = 1
  analysisStage.value = 'done'
  result.value = data
  engineSel.value = data.engine || 'auto'
  state.value = 'ready'
  fetchHistory()
  backfillBpm(data)
}

const stageLabels = {
  queued: '排队中',
  extracting: '正在提取和弦',
  saving: '正在保存结果',
  done: '识别完成',
}

const progressLabel = computed(() => stageLabels[analysisStage.value] || '处理中')

async function waitForTask(taskId, token) {
  while (token === pollToken) {
    const resp = await fetch(`/api/tasks/${taskId}`)
    if (!resp.ok) {
      let detail = `任务查询失败（${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    const data = await resp.json()
    analysisProgress.value = Number(data.progress) || 0
    analysisStage.value = data.stage || data.status || 'queued'
    if (data.status === 'done') return data.result
    if (data.status === 'error') throw new Error(data.error || '后台识别失败')
    await new Promise((resolve) => setTimeout(resolve, 800))
  }
  throw new Error('分析已取消')
}

function onFileSelected(file) {
  selectedFile.value = file
  uploadCache.value = null
  uploadConfirmOpen.value = true
}

function cancelUploadConfirm() {
  if (uploadBusy.value) return
  uploadConfirmOpen.value = false
  uploadCache.value = null
  selectedFile.value = null
}

async function confirmUpload({ engine }) {
  if (!selectedFile.value) return
  uploadBusy.value = true
  try {
    await upload(selectedFile.value, engine, selectedFile.value.name)
  } finally {
    uploadBusy.value = false
  }
}

function reselectUpload() {
  uploadZoneRef.value?.pick()
}

function openCachedUpload() {
  const cached = uploadCache.value
  if (!cached) return
  uploadConfirmOpen.value = false
  uploadCache.value = null
  applyResult(cached)
}

function reanalyzeCachedUpload() {
  const cached = uploadCache.value
  if (!cached) return
  uploadConfirmOpen.value = false
  uploadCache.value = null
  requestReanalyze(cached)
}

async function upload(file, engine = 'auto', filename = file.name) {
  pollToken += 1
  state.value = 'analyzing'
  analyzingKind.value = 'analyze'
  analysisProgress.value = 0
  analysisStage.value = 'queued'
  errorMsg.value = ''
  const form = new FormData()
  form.append('file', file)
  form.append('engine', engine)
  form.append('filename', filename)
  try {
    const resp = await fetch('/api/analyze', { method: 'POST', body: form })
    if (!resp.ok) {
      let detail = `请求失败（${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    let data = await resp.json()
    if (data.cached) {
      state.value = 'idle'
      uploadCache.value = data
      return
    }
    uploadConfirmOpen.value = false
    if (resp.status === 202 && data.task_id) {
      data = await waitForTask(data.task_id, pollToken)
    }
    if (!data.chords?.length) throw new Error('未识别到任何和弦，请更换音频重试')
    applyResult(data)
  } catch (err) {
    uploadConfirmOpen.value = false
    errorMsg.value = err.message || '上传或识别失败，请重试'
    state.value = 'error'
  }
}

async function loadHistoryItem(item) {
  state.value = 'analyzing'
  analyzingKind.value = 'history'
  errorMsg.value = ''
  try {
    const resp = await fetch(`/api/analyses/${item.id}`)
    if (!resp.ok) {
      let detail = `请求失败（${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    const data = await resp.json()
    if (!data.chords?.length) throw new Error('记录数据不完整')
    applyResult(data)
  } catch (err) {
    errorMsg.value = err.message || '载入历史记录失败'
    state.value = 'error'
  }
}

async function reanalyzeHistoryItem(item, engine) {
  pollToken += 1
  const token = pollToken
  state.value = 'analyzing'
  analyzingKind.value = 'reanalyze'
  analysisProgress.value = 0
  analysisStage.value = 'queued'
  reanalyzingId.value = item?.id || ''
  errorMsg.value = ''
  const eng = engine || item?.engine || 'auto'
  try {
    const resp = await fetch(
      `/api/analyses/${item.id}/reanalyze?engine=${encodeURIComponent(eng)}`,
      { method: 'POST' },
    )
    if (!resp.ok) {
      let detail = `请求失败（${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    let data = await resp.json()
    if (resp.status === 202 && data.task_id) {
      data = await waitForTask(data.task_id, token)
    }
    if (!data.chords?.length) throw new Error('未识别到任何和弦')
    applyResult(data)
  } catch (err) {
    errorMsg.value = err.message || '重新识别失败'
    state.value = 'error'
  } finally {
    reanalyzingId.value = ''
  }
}

// 重新识别入口：记录已人工编辑时先确认（机器结果将覆盖）
function requestReanalyze(item, engine) {
  if (!engine) {
    reanalyzeConfirmItem.value = item
    return
  }
  startReanalyze(item, engine)
}

function startReanalyze(item, engine) {
  const edited = item?.edited || (result.value && item.id === result.value.id && result.value.edited)
  if (edited) {
    confirmRef.value = {
      title: '重新识别将覆盖人工修改',
      message: '该记录已有人工编辑的和弦。重新识别会丢弃这些修改，回到机器识别结果。是否继续？',
      confirmText: '继续重新识别',
      run: () => reanalyzeHistoryItem(item, engine),
    }
  } else {
    reanalyzeHistoryItem(item, engine)
  }
}

function cancelReanalyzeConfirm() {
  if (!reanalyzingId.value) reanalyzeConfirmItem.value = null
}

function confirmReanalyze({ engine }) {
  const item = reanalyzeConfirmItem.value
  reanalyzeConfirmItem.value = null
  if (item) startReanalyze(item, engine)
}

async function deleteHistoryItem(item) {
  try {
    const resp = await fetch(`/api/analyses/${item.id}`, { method: 'DELETE' })
    if (!resp.ok) {
      let detail = `删除失败（${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    fetchHistory()
  } catch (err) {
    errorMsg.value = err.message || '删除失败'
    state.value = 'error'
  }
}

/* ── 编辑工作台 ── */
function openEditor() {
  bus.emit('player:pause') // 打开编辑前暂停播放
  document.body.classList.add('modal-open')
  editOpen.value = true
}

function onWorkspaceSaved(data) {
  editOpen.value = false
  document.body.classList.remove('modal-open')
  applyResult(data)
}

function onWorkspaceClose() {
  editOpen.value = false
  document.body.classList.remove('modal-open')
}

function reset() {
  pollToken += 1
  state.value = 'idle'
  result.value = null
  errorMsg.value = ''
  selectedFile.value = null
  uploadConfirmOpen.value = false
  uploadCache.value = null
  reanalyzeConfirmItem.value = null
  editOpen.value = false
  document.body.classList.remove('modal-open')
}

const sourceLabel = (s) =>
  s === 'deepchroma'
    ? 'DeepChroma · CRF'
    : s === 'chordino'
      ? 'Chordino · NNLS-Chroma'
      : s === 'lv-chordia'
        ? 'LV-Chordia'
        : '色度模板匹配（回退）'

const ENGINE_OPTIONS = [
  { value: 'auto', label: '自动' },
  { value: 'deepchroma', label: 'DeepChroma' },
  { value: 'chordino', label: 'Chordino' },
  { value: 'lv-chordia', label: 'LV-Chordia' },
]
const engineSel = ref('auto') // 当前展示的引擎

function engineStatus(value) {
  return engineCapabilities.value?.engines?.[value] || null
}

function engineAvailable(value) {
  return engineStatus(value)?.available !== false
}

function engineOptionTitle(value) {
  const status = engineStatus(value)
  return engineAvailable(value)
    ? `切换到 ${ENGINE_OPTIONS.find((item) => item.value === value)?.label || value}`
    : `当前系统不支持：${status?.reason || '依赖不可用'}`
}

async function switchEngine(eng) {
  if (!result.value || eng === engineSel.value || !engineAvailable(eng)) return
  requestReanalyze({ id: result.value.id, edited: result.value.edited }, eng)
}

const analyzingTitle = computed(() =>
  analyzingKind.value === 'history'
    ? '正在载入历史记录'
    : analyzingKind.value === 'reanalyze'
      ? '正在重新识别'
      : '正在识别和弦',
)
const analyzingSub = computed(() =>
  analyzingKind.value === 'history'
    ? '正在从缓存中读取该曲目的和弦数据'
    : analyzingKind.value === 'reanalyze'
      ? '正在重新提取该曲目的和弦 · 时长较长的文件可能需要数十秒'
      : '正在解析音频并提取和声序列 · 时长较长的文件可能需要数十秒',
)

// 和弦显示档位：简化（归一化后的根音+性质） / 完整（保留扩展与转位）
const viewMode = ref('simple') // simple | full

const displayChords = computed(() => {
  if (!result.value) return []
  if (viewMode.value === 'simple') {
    return result.value.chords_simple?.length
      ? result.value.chords_simple
      : result.value.chords
  }
  return result.value.chords
})
</script>

<template>
  <div class="page">
    <header class="masthead">
      <div class="wordmark">
        <span class="wordmark-serif">和弦</span>
        <span class="wordmark-latin">CHORD · RECOGNITION</span>
      </div>
      <p class="tagline">上传一段音乐，在时间轴上读它的和声。</p>
    </header>

    <hr class="divider" />

    <main class="stage" :class="{ 'stage-result': state === 'ready' && result }">
      <!-- 上传 -->
      <section v-if="state === 'idle'" class="fade-in">
        <UploadZone ref="uploadZoneRef" @select="onFileSelected" />
        <p class="stage-note">
          音频仅用于本次识别，不上传至任何第三方服务。
        </p>
        <HistoryList
          v-if="history.length"
          :items="history"
          :busy-id="reanalyzingId"
          @open="loadHistoryItem"
          @delete="deleteHistoryItem"
          @reanalyze="requestReanalyze"
        />
      </section>

      <!-- 识别中 / 载入历史 -->
      <section v-else-if="state === 'analyzing'" class="analyzing fade-in">
        <div class="spinner"></div>
        <h2 class="analyzing-title">{{ analyzingTitle }}</h2>
        <p class="analyzing-sub">{{ analyzingSub }}</p>
        <div class="progress-track" role="progressbar" :aria-valuenow="Math.round(analysisProgress * 100)" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-fill" :style="{ width: `${Math.max(4, analysisProgress * 100)}%` }"></div>
        </div>
        <p class="progress-meta">{{ progressLabel }} · {{ Math.round(analysisProgress * 100) }}%</p>
        <p v-if="analyzingKind === 'analyze'" class="analyzing-file">
          {{ selectedFile?.name }}
        </p>
      </section>

      <!-- 结果 -->
      <section v-else-if="state === 'ready' && result" class="fade-in">
        <div class="result-topbar">
          <button class="btn-ghost result-back" title="返回上传页" @click="reset">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M8.5 4 3 10l5.5 6M3.5 10H17" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            返回
          </button>
        </div>
        <ChordTimeline
          :audio-url="result.audio_url"
          :chords="displayChords"
          :filename="result.filename"
          :duration="result.duration"
        />
        <div class="result-foot">
          <div class="rf-row">
            <span class="caption">识别引擎</span>
            <div
              class="seg"
              :title="'当前实际使用：' + sourceLabel(result.source)"
            >
              <button
                v-for="o in ENGINE_OPTIONS"
                :key="o.value"
                :class="{ on: engineSel === o.value, unavailable: !engineAvailable(o.value), recommended: o.value === preferredEngine && engineAvailable(o.value) }"
                :aria-pressed="engineSel === o.value"
                :disabled="!engineAvailable(o.value)"
                :title="engineOptionTitle(o.value)"
                @click="switchEngine(o.value)"
              >{{ o.label }}</button>
            </div>
            <span class="dot-sep"></span>
            <span class="caption">和弦标记</span>
            <span class="engine">{{ displayChords.length }} 处变化</span>
            <span
              v-if="result.bpm != null"
              class="bpm-chip mono"
              :title="'检测到的速度（每分钟拍数）'"
            >♩ = {{ result.bpm }}</span>
            <span
              v-if="result.edited"
              class="edited-badge"
              :title="result.edited_at ? '人工编辑于 ' + result.edited_at : '含人工编辑'"
            >已编辑</span>
            <span
              v-if="result.cached"
              class="cached-badge"
              :title="result.created_at ? '首次分析于 ' + result.created_at : '来自本地缓存'"
            >缓存命中</span>
            <span class="grow"></span>
            <span class="caption seg-label">显示</span>
            <div class="seg">
              <button
                :class="{ on: viewMode === 'simple' }"
                :aria-pressed="viewMode === 'simple'"
                @click="viewMode = 'simple'"
              >简化</button>
              <button
                :class="{ on: viewMode === 'full' }"
                :aria-pressed="viewMode === 'full'"
                @click="viewMode = 'full'"
              >完整</button>
            </div>
          </div>
          <div class="rf-row rf-actions">
            <span class="caption">{{ result.filename }}</span>
            <span class="grow"></span>
            <button class="btn-ghost" title="打开编辑工作台：修改和弦名、移动位置、增删标记" @click="openEditor">
              <svg class="i-pen" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path
                  d="M12.8 3.6l3.6 3.6L7.2 16.4l-4.2.6.6-4.2z"
                  stroke="currentColor"
                  stroke-width="1.2"
                  stroke-linejoin="round"
                />
              </svg>
              编辑
            </button>
            <ExportMenu
              :chords="displayChords"
              :filename="result.filename"
              :duration="result.duration"
              :source="result.source"
            />
            <button class="btn-ghost" @click="reset">重新上传</button>
          </div>
        </div>
      </section>

      <!-- 错误 -->
      <section v-else class="error fade-in">
        <p class="error-icon">!</p>
        <h2 class="error-title">识别未完成</h2>
        <p class="error-msg">{{ errorMsg }}</p>
        <button class="btn-ghost" @click="reset">返回重试</button>
      </section>
    </main>

    <!-- 编辑工作台（悬浮） -->
    <EditWorkspace
      v-if="editOpen && result"
      :analysis="result"
      @close="onWorkspaceClose"
      @saved="onWorkspaceSaved"
    />

    <!-- 上传后的分析设置与缓存确认 -->
    <AnalyzeConfirm
      v-if="uploadConfirmOpen && selectedFile"
      :file="selectedFile"
      :busy="uploadBusy"
      :cached-result="uploadCache"
      :capabilities="engineCapabilities"
      :recommended-engine="preferredEngine"
      @confirm="confirmUpload"
      @cancel="cancelUploadConfirm"
      @reselect="reselectUpload"
      @open-cache="openCachedUpload"
      @reanalyze-cache="reanalyzeCachedUpload"
    />

    <AnalyzeConfirm
      v-if="reanalyzeConfirmItem"
      mode="reanalyze"
      :reanalyze-item="reanalyzeConfirmItem"
      :busy="Boolean(reanalyzingId)"
      :capabilities="engineCapabilities"
      :recommended-engine="preferredEngine"
      @confirm="confirmReanalyze"
      @cancel="cancelReanalyzeConfirm"
    />

    <!-- 覆盖人工修改确认 -->
    <ConfirmDialog
      v-if="confirmRef"
      :title="confirmRef.title"
      :message="confirmRef.message"
      :confirm-text="confirmRef.confirmText"
      @confirm="confirmRef.run(); confirmRef = null"
      @cancel="confirmRef = null"
    />
  </div>
</template>

<style scoped>
.page {
  max-width: 860px;
  margin: 0 auto;
  padding: 72px 32px 48px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.masthead {
  margin-bottom: 36px;
}
.wordmark {
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.wordmark-serif {
  font-family: var(--font-serif);
  font-size: 34px;
  letter-spacing: 0.14em;
  color: var(--text);
}
.wordmark-latin {
  font-size: 11px;
  letter-spacing: 0.42em;
  color: var(--text-faint);
  text-transform: uppercase;
}
.tagline {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-dim);
  letter-spacing: 0.06em;
}

.stage {
  flex: 1;
  padding-top: 44px;
}

.stage-result {
  padding-top: 18px;
}

.stage-note {
  margin-top: 18px;
  text-align: center;
  font-size: 12px;
  color: var(--text-faint);
  letter-spacing: 0.05em;
}

.result-topbar {
  height: 30px;
  display: flex;
  align-items: flex-start;
}

.result-back {
  padding: 3px 8px 3px 2px;
  border-color: transparent;
  background: transparent;
  font-size: 12px;
}

.result-back svg {
  width: 16px;
  height: 16px;
}

.result-back:hover {
  border-color: transparent;
  background: transparent;
  color: var(--accent);
}

/* 识别中 */
.analyzing {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 90px 0 120px;
}
.analyzing-title {
  margin-top: 18px;
  font-family: var(--font-serif);
  font-size: 21px;
  font-weight: 500;
  letter-spacing: 0.12em;
}
.analyzing-sub {
  font-size: 13px;
  color: var(--text-dim);
}
.progress-track {
  width: min(360px, 80vw);
  height: 3px;
  margin-top: 18px;
  overflow: hidden;
  background: var(--border);
}
.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.35s ease;
}
.progress-meta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}
.analyzing-file {
  margin-top: 14px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-faint);
}

/* 结果页脚 */
.result-foot {
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rf-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.rf-actions {
  font-size: 12px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.engine {
  font-size: 12px;
  color: var(--text-dim);
  font-family: var(--font-mono);
  white-space: nowrap;
}
.dot-sep {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-faint);
  margin: 0 6px;
}
.cached-badge {
  font-size: 10.5px;
  letter-spacing: 0.12em;
  color: var(--accent);
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  border-radius: 999px;
  padding: 2px 10px;
  white-space: nowrap;
}
.bpm-chip {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--accent);
  border: 1px solid var(--accent-line);
  border-radius: 999px;
  padding: 2px 10px;
  white-space: nowrap;
}
.edited-badge {
  font-size: 10.5px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  border: 1px dashed var(--border);
  border-radius: 999px;
  padding: 2px 10px;
  white-space: nowrap;
}
.i-pen {
  width: 13px;
  height: 13px;
}
.seg-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.seg {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
  flex: none;
}
.seg button {
  padding: 5px 14px;
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--text-dim);
  transition: color 0.25s ease, background 0.25s ease;
}
.seg button + button {
  border-left: 1px solid var(--border);
}
.seg button:hover {
  color: var(--text);
}
.seg button.on {
  color: var(--accent);
  background: var(--accent-soft);
}

.seg button.recommended:not(.on) {
  color: var(--accent);
}

.seg button.unavailable {
  color: var(--text-faint);
  cursor: not-allowed;
  opacity: 0.45;
}

.seg button.unavailable:hover {
  color: var(--text-faint);
}
.grow {
  flex: 1;
}

/* 错误 */
.error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 90px 0 120px;
}
.error-icon {
  width: 44px;
  height: 44px;
  border: 1px solid var(--border);
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--font-serif);
  color: var(--danger);
  font-size: 20px;
}
.error-title {
  margin-top: 10px;
  font-family: var(--font-serif);
  font-size: 21px;
  font-weight: 500;
  letter-spacing: 0.12em;
}
.error-msg {
  font-size: 13px;
  color: var(--text-dim);
  max-width: 460px;
  text-align: center;
  margin-bottom: 12px;
}

.foot {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--border-soft);
  display: flex;
  justify-content: center;
  gap: 14px;
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--text-faint);
  text-transform: uppercase;
}
.foot-mid {
  color: var(--border);
}
</style>
