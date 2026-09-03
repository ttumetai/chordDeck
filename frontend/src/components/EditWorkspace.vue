<script setup>
// DAW 风格编辑工作台：刻度尺 + 音轨泳道 + 和弦色块
// 缩放/平移/网格抽稀/吸附/边缘与整体拖动/双击分割与改名
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import PianoKeyboard from './PianoKeyboard.vue'
import { keyboardHighlights, parseChordLabel } from '../lib/music.js'

const props = defineProps({
  analysis: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

/* ── 工作副本 ── */
let uidSeed = 0
const uid = () => `r${++uidSeed}_${Math.random().toString(36).slice(2, 7)}`

function cloneRows(chords) {
  return (chords || []).map((c) => ({
    uid: uid(),
    timestamp: Number(c.timestamp) || 0,
    chord: String(c.chord || ''),
  }))
}

const duration = computed(() => Math.max(Number(props.analysis.duration) || 0, 0.001))
const rows = ref(cloneRows(props.analysis.chords))

function snapshotKey() {
  return rows.value.map((r) => `${r.timestamp.toFixed(3)}|${r.chord}`).join('\n')
}
const originKey = ref('')
const dirty = ref(false)
const markDirty = () => (dirty.value = snapshotKey() !== originKey.value)

function resort() {
  rows.value.sort((a, b) => a.timestamp - b.timestamp)
}

/* ── 节拍/网格数据 ── */
const beats = ref([])
const bpm = ref(props.analysis.bpm ?? null)
const beatsLoading = ref(true)
const density = ref('beat')
const beatsPerBar = ref(4)
const snapOn = ref(true)

onMounted(async () => {
  originKey.value = snapshotKey()
  document.body.classList.add('modal-open')
  window.addEventListener('keydown', onKey)
  try {
    const resp = await fetch(`/api/analyses/${props.analysis.id}/beats`)
    if (resp.ok) {
      const data = await resp.json()
      beats.value = data.beats || []
      if (data.bpm && !bpm.value) bpm.value = data.bpm
    }
  } catch {
    /* ignore */
  } finally {
    beatsLoading.value = false
  }
  await nextTick()
  applyDefaultZoom() // 默认缩放：可视范围约 4 个小节
})

onUnmounted(() => {
  document.body.classList.remove('modal-open')
  window.removeEventListener('keydown', onKey)
  endPan()
  stopPreview()
})

const DENSITY_OPTIONS = [
  { value: 'bar', label: '小节' },
  { value: 'beat', label: '拍' },
  { value: 'eighth', label: '8分' },
  { value: 'sixteenth', label: '16分' },
]

/* ── 视图/缩放 ── */
const viewportRef = ref(null)
const viewW = ref(900)
const pxPerSec = ref(40)
const scrollLeft = ref(0)

let ro = null
function measure() {
  const w = viewportRef.value?.clientWidth
  if (w && w > 0) viewW.value = w
}
onMounted(() => {
  ro = new ResizeObserver(measure)
  ro.observe(viewportRef.value)
})
onUnmounted(() => ro?.disconnect())

const contentW = computed(() => duration.value * pxPerSec.value)

function computeFit() {
  const w = viewportRef.value?.clientWidth || viewW.value
  pxPerSec.value = Math.max(2, w / duration.value)
}

/* 平均小节长度（按节拍边界计）；无节拍数据返回 null */
function barLength() {
  const bts = beats.value
  if (!bts.length) return null
  const bounds = []
  bts.forEach((b, i) => {
    if (i % beatsPerBar.value === 0) bounds.push(b)
  })
  if (bounds.length >= 2) {
    return (bounds[bounds.length - 1] - bounds[0]) / (bounds.length - 1)
  }
  return null
}

/* 默认缩放：让 n 个小节铺满可视宽度 */
function zoomForBars(n) {
  const w = viewportRef.value?.clientWidth || viewW.value
  const bl = barLength()
  if (bl && bl > 0) {
    pxPerSec.value = Math.min(900, Math.max(2, w / (n * bl)))
  } else {
    pxPerSec.value = Math.min(900, Math.max(2, w / duration.value))
  }
}
function applyDefaultZoom() {
  zoomForBars(4)
}

/* 拖动空白处/刻度尺平移时间轴 */
const panning = ref(false)
const panStart = ref(null)
const justDragged = ref(false)
function startPan(e) {
  if (panStart.value) return
  e.preventDefault()
  justDragged.value = false
  panning.value = true
  panStart.value = { x: e.clientX, scroll: viewportRef.value.scrollLeft }
  window.addEventListener('pointermove', onPanMove)
  window.addEventListener('pointerup', endPan)
}
function onPanMove(e) {
  const p = panStart.value
  if (!p || !viewportRef.value) return
  if (Math.abs(e.clientX - p.x) > 3) justDragged.value = true
  viewportRef.value.scrollLeft = p.scroll - (e.clientX - p.x)
}
function endPan() {
  panning.value = false
  panStart.value = null
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', endPan)
}
function zoomBy(factor, anchorClientX = null) {
  const old = pxPerSec.value
  const next = Math.min(900, Math.max(2, old * factor))
  if (next === old) return
  const el = viewportRef.value
  if (anchorClientX !== null && el) {
    const rect = el.getBoundingClientRect()
    const anchorPx = scrollLeft.value + (anchorClientX - rect.left)
    const time = anchorPx / old
    pxPerSec.value = next
    el.scrollLeft = time * next - (anchorClientX - rect.left)
  } else {
    pxPerSec.value = next
  }
}

function onCanvasWheel(e) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    zoomBy(e.deltaY < 0 ? 1.35 : 1 / 1.35, e.clientX)
    return
  }
  // 普通滚轮：横向平移
  const el = viewportRef.value
  if (el) el.scrollLeft += e.deltaY || e.deltaX
}

const fmtSec = (t) => {
  const s = Math.max(0, t)
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
const fmt10 = (t) => {
  const s = Math.max(0, t)
  const m = Math.floor(s / 60)
  const sec = s - m * 60
  return `${String(m).padStart(2, '0')}:${sec.toFixed(1).padStart(4, '0')}`
}
const fmtDur = (a, b) => fmt10(Math.max(0, b - a))

/* ── 网格线（自动抽稀：保持屏上 ≥10px 间距） ── */
const gridRender = computed(() => {
  const lines = []
  const secTicks = []
  const barNo = []
  // 秒刻度（自适应；无节拍时仍提供时间标尺）
  const px = pxPerSec.value
  const secStep = [0.5, 1, 2, 5, 10, 15, 30, 60].find((s) => s * px >= 70) || 120
  for (let t = 0; t <= duration.value; t += secStep) {
    secTicks.push({ x: t * px, label: fmtSec(t) })
  }
  if (!beats.value.length) return { lines, secTicks, barNo }

  // 可选刻度集（由粗到细）
  const candidates = []
  beats.value.forEach((b, i) => {
    if (i % beatsPerBar.value === 0) candidates.push({ t: b, kind: 'bar', i })
  })
  if (density.value !== 'bar') {
    beats.value.forEach((b) => candidates.push({ t: b, kind: 'beat' }))
    const n = density.value === 'eighth' ? 2 : density.value === 'sixteenth' ? 4 : 0
    for (let i = 0; i + 1 < beats.value.length; i++) {
      const a = beats.value[i]
      const b = beats.value[i + 1]
      for (let k = 1; k < n; k++) {
        candidates.push({ t: a + ((b - a) * k) / n, kind: n === 2 ? 'eighth' : 'sixteenth' })
      }
    }
  }
  // 抽稀：保持相邻 ≥ MIN_PX；细分优先丢弃
  const MIN_PX = 9
  const order = { bar: 3, beat: 2, eighth: 1, sixteenth: 0 }
  candidates.sort((a, b) => a.t - b.t)
  const keep = []
  for (const c of candidates) {
    const prev = keep.length ? keep[keep.length - 1] : null
    if (prev && (c.t - prev.t) * px < MIN_PX) {
      if (order[c.kind] > order[prev.kind]) keep[keep.length - 1] = c
      continue
    }
    keep.push(c)
  }
  for (const c of keep) lines.push({ x: c.t * px, kind: c.kind })

  // 小节号（自适应跳号）
  const barXs = []
  beats.value.forEach((b, i) => {
    if (i % beatsPerBar.value === 0) barXs.push({ t: b, n: Math.floor(i / beatsPerBar.value) + 1 })
  })
  const barPx = barXs.length > 1 ? (barXs[1].t - barXs[0].t) * px : 0
  const step = barPx >= 46 ? 1 : barPx >= 24 ? 2 : 4
  barXs.forEach((b, i) => {
    if (i % step === 0) barNo.push({ x: b.t * px, label: String(b.n) })
  })
  return { lines, secTicks, barNo }
})

const px = () => pxPerSec.value
const tAt = (clientX) => {
  const rect = viewportRef.value.getBoundingClientRect()
  const rel = clientX - rect.left + scrollLeft.value
  return rel / px()
}

/* ── 吸附 ── */
function snapT(t) {
  if (!snapOn.value || !beats.value.length) return t
  const grid = []
  const bts = beats.value
  const barOnly = density.value === 'bar'
  const n =
    density.value === 'eighth' ? 2 : density.value === 'sixteenth' ? 4 : 0
  for (let i = 0; i < bts.length; i++) {
    if (barOnly && i % beatsPerBar.value !== 0) continue
    grid.push(bts[i])
    if (n > 1 && i + 1 < bts.length) {
      for (let k = 1; k < n; k++) grid.push(bts[i] + ((bts[i + 1] - bts[i]) * k) / n)
    }
  }
  if (!grid.length) return t
  let best = grid[0]
  let bd = Infinity
  for (const g of grid) {
    const d = Math.abs(g - t)
    if (d < bd) {
      bd = d
      best = g
    }
  }
  return Math.round(best * 1000) / 1000
}

/* ── 选择 / 块几何 ── */
const sel = ref(-1)
const HIT = 9 // 边缘命中像素

const blockGeom = computed(() => {
  const list = rows.value
  return list.map((r, i) => {
    const t0 = r.timestamp
    const t1 = i + 1 < list.length ? list[i + 1].timestamp : duration.value
    return {
      idx: i,
      t0,
      t1,
      x0: t0 * px(),
      w: Math.max((t1 - t0) * px(), 0),
      dur: Math.max(t1 - t0, 0),
    }
  })
})

function hitTest(clientX) {
  const t = tAt(clientX)
  const g = blockGeom.value
  // 边界优先
  for (const b of g) {
    const xEdgeL = b.x0
    const xEdgeR = b.x0 + b.w
    if (Math.abs(t * px() - xEdgeL) <= HIT) return { mode: 'edgeL', idx: b.idx }
    if (Math.abs(t * px() - xEdgeR) <= HIT) return { mode: 'edgeR', idx: b.idx }
  }
  for (const b of g) {
    if (t >= b.t0 - 0.001 && t <= b.t1 + 0.001) return { mode: 'body', idx: b.idx }
  }
  return null
}

/* ── 拖动 ── */
const drag = ref(null) // { mode, idx, startClientX, startT }
const dragPreview = ref(null) // { t0, t1 }

function onLaneDown(e, idx) {
  justDragged.value = false
  const hit = hitTest(e.clientX)
  if (!hit) {
    sel.value = -1
    startPan(e) // 空白处按住拖动 = 平移时间轴
    return
  }
  sel.value = hit.idx
  const b = blockGeom.value[hit.idx]
  drag.value = {
    mode: hit.mode,
    idx: hit.idx,
    startClientX: e.clientX,
    startT: b.t0,
  }
  dragPreview.value = { t0: b.t0, t1: b.t1 }
  viewportRef.value.setPointerCapture(e.pointerId)
}

function onLaneMove(e) {
  if (!drag.value) return
  if (Math.abs(e.clientX - drag.value.startClientX) > 3) justDragged.value = true
  const d = drag.value
  const dt = (e.clientX - d.startClientX) / px()
  const list = rows.value
  const i = d.idx
  if (d.mode === 'edgeL' || d.mode === 'body') {
    let lo = i > 0 ? list[i - 1].timestamp : 0
    let hi = i + 1 < list.length ? list[i + 1].timestamp : duration.value
    let t0 = Math.min(Math.max(d.startT + dt, lo), hi)
    if (d.mode === 'body' && i + 1 < list.length) {
      // 整体平移：保持长度，双边界同移
      const dur = blockGeom.value[i].dur
      const hi2 = hi - dur
      t0 = Math.min(Math.max(t0, lo), Math.max(lo, hi2))
      dragPreview.value = { t0, t1: t0 + dur }
    } else {
      // edgeL；末块的 body 拖动等价于移动起点（末端固定于音频结束）
      dragPreview.value = { t0, t1: blockGeom.value[i].t1 }
    }
  } else {
    const lo = i > 0 ? list[i - 1].timestamp : 0
    const hi = duration.value
    const t1 = Math.min(Math.max(blockGeom.value[i].t1 + dt, lo), hi)
    dragPreview.value = { t0: blockGeom.value[i].t0, t1 }
  }
}

function onLaneUp() {
  if (!drag.value) return
  const d = drag.value
  const i = d.idx
  const p = dragPreview.value
  if (p) {
    if (d.mode !== 'edgeR') {
      rows.value[i].timestamp = snapT(p.t0)
      if (d.mode === 'body' && i + 1 < rows.value.length) {
        rows.value[i + 1].timestamp = rows.value[i].timestamp + (p.t1 - p.t0)
      }
    } else if (i + 1 < rows.value.length) {
      rows.value[i + 1].timestamp = snapT(p.t1)
    }
    // 夹取顺序
    let prev = 0
    for (const r of rows.value) {
      r.timestamp = Math.max(r.timestamp, prev)
      prev = r.timestamp
    }
    markDirty()
  }
  drag.value = null
  dragPreview.value = null
}

function onLaneDbl(e) {
  const t = tAt(e.clientX)
  const g = blockGeom.value
  const b = g.find((x) => t > x.t0 + 0.02 && t < x.t1 - 0.02)
  if (!b) return
  splitBlock(b.idx, snapT(t))
}

function onTimelineClick(e) {
  if (justDragged.value || e.detail > 1) {
    justDragged.value = false
    return
  }
  setPlayAnchor(tAt(e.clientX))
}

function splitBlock(i, t) {
  const list = rows.value
  const t0 = list[i].timestamp
  const t1 = i + 1 < list.length ? list[i + 1].timestamp : duration.value
  const tt = Math.min(Math.max(t, t0 + 0.03), t1 - 0.03)
  if (tt <= t0 + 0.03 || tt >= t1 - 0.03) return
  rows.value.splice(i + 1, 0, { uid: uid(), timestamp: tt, chord: list[i].chord })
  resort()
  sel.value = rows.value.findIndex((r) => r.timestamp === tt)
  markDirty()
}

function removeBlock(i) {
  if (rows.value.length <= 1) return
  if (i === 0) {
    rows.value[1].timestamp = rows.value[0].timestamp // 第二段接管头部
    rows.value.splice(0, 1)
  } else {
    rows.value.splice(i, 1)
  }
  resort()
  sel.value = -1
  markDirty()
}

function nudgeStart(dt) {
  if (sel.value < 0) return
  const i = sel.value
  const lo = i > 0 ? rows.value[i - 1].timestamp : 0
  const hi = i + 1 < rows.value.length ? rows.value[i + 1].timestamp : duration.value
  rows.value[i].timestamp = Math.round(Math.min(Math.max(rows.value[i].timestamp + dt, lo), hi) * 100) / 100
  markDirty()
}

/* ── 校验 / 预览 ── */
const invalidSel = computed(() => {
  if (sel.value < 0) return false
  const name = rows.value[sel.value].chord.trim()
  return name !== '' && name !== 'N' && !parseChordLabel(name)
})
const selParsed = computed(() => {
  if (sel.value < 0) return null
  const name = rows.value[sel.value].chord.trim()
  if (!name || name === 'N') return null
  return parseChordLabel(name)
})
const previewHighlight = computed(() =>
  selParsed.value ? Object.fromEntries(keyboardHighlights(selParsed.value)) : null,
)
const anyInvalid = computed(() => {
  const bad = []
  rows.value.forEach((r, i) => {
    const name = r.chord.trim()
    if (name !== '' && name !== 'N' && !parseChordLabel(name)) bad.push(i + 1)
  })
  return bad
})

/* ── 键盘快捷键 ── */
function onKey(e) {
  if (e.target.closest('input, textarea, select')) return
  if (e.code === 'Space' && !e.repeat) {
    e.preventDefault()
    togglePreview()
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    if (sel.value >= 0) {
      e.preventDefault()
      removeBlock(sel.value)
    }
  } else if (e.key === 'Escape') {
    drag.value = null
    dragPreview.value = null
    sel.value = -1
  } else if (e.key === 'ArrowLeft' && e.shiftKey) {
    e.preventDefault()
    nudgeStart(-0.1)
  } else if (e.key === 'ArrowRight' && e.shiftKey) {
    e.preventDefault()
    nudgeStart(0.1)
  }
}

/* ── 保存 / 取消 ── */
const saving = ref(false)
const saveError = ref('')
const cancelAsk = ref(false)
let cancelTimer = null

async function save() {
  if (saving.value || anyInvalid.value.length) return
  saving.value = true
  saveError.value = ''
  const payload = rows.value.map((r) => ({
    timestamp: Math.round(r.timestamp * 1000) / 1000,
    chord: r.chord.trim() || 'N',
  }))
  try {
    const resp = await fetch(`/api/analyses/${props.analysis.id}/chords`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chords: payload }),
    })
    if (!resp.ok) {
      let detail = `保存失败（${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) detail = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    emit('saved', await resp.json())
  } catch (err) {
    saveError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function close() {
  if (dirty.value && !cancelAsk.value) {
    cancelAsk.value = true
    clearTimeout(cancelTimer)
    cancelTimer = setTimeout(() => (cancelAsk.value = false), 2600)
    return
  }
  emit('close')
}

const canSave = computed(
  () => dirty.value && !anyInvalid.value.length && !saving.value,
)

const selRow = computed(() => (sel.value >= 0 ? rows.value[sel.value] : null))

/* ── 编辑器试听 ── */
const previewAudio = ref(null)
const previewPlaying = ref(false)
const previewCurrent = ref(0)
const previewDuration = ref(Number(props.analysis.duration) || 0)
const previewAnchor = ref(0)

const previewCursor = computed(() =>
  (previewPlaying.value ? previewCurrent.value : previewAnchor.value) * px(),
)

const fmtPreview = (t) => {
  const s = Math.max(0, Math.floor(Number(t) || 0))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function togglePreview() {
  const audio = previewAudio.value
  if (!audio) return
  if (audio.paused) {
    audio.currentTime = previewAnchor.value
    audio.play().then(() => (previewPlaying.value = true)).catch(() => {})
  } else {
    audio.pause()
    previewPlaying.value = false
  }
}

function setPlayAnchor(t) {
  const next = Math.min(duration.value, Math.max(0, snapT(t)))
  previewAnchor.value = next
  previewCurrent.value = next
  if (previewAudio.value) previewAudio.value.currentTime = next
}

function onPreviewEnded() {
  previewPlaying.value = false
  previewCurrent.value = previewDuration.value
}

function onPreviewMetadata(e) {
  if (Number.isFinite(e.target?.duration) && e.target.duration > 0) {
    previewDuration.value = e.target.duration
  }
}

function stopPreview() {
  const audio = previewAudio.value
  if (audio) audio.pause()
  previewPlaying.value = false
}
</script>

<template>
  <div class="ws-overlay" @click.self="close">
    <div class="ws-panel">
      <!-- 标题栏 -->
      <header class="ws-head">
        <audio
          ref="previewAudio"
          class="ws-audio"
          :src="analysis.audio_url"
          preload="metadata"
          @loadedmetadata="onPreviewMetadata"
          @timeupdate="previewCurrent = $event.target.currentTime || 0"
          @ended="onPreviewEnded"
        ></audio>
        <div class="ws-title-box">
          <h2 class="ws-title">编辑和弦</h2>
          <span class="ws-file" :title="analysis.filename">{{ analysis.filename }}</span>
        </div>
        <div class="ws-head-right">
          <span v-if="beatsLoading" class="caption bpm-loading">识别节拍…</span>
          <span v-else-if="bpm" class="bpm-chip mono">♩ = {{ bpm }}</span>
          <span v-else class="caption bpm-none">未检测到节拍</span>
          <span class="ws-preview-time mono">{{ fmtPreview(previewCurrent) }} / {{ fmtPreview(previewDuration) }}</span>
          <button class="ws-play" :aria-label="previewPlaying ? '暂停原曲' : '播放原曲'" :title="previewPlaying ? '暂停原曲' : '播放原曲（从定位点开始）'" @click="togglePreview">
            <svg v-if="!previewPlaying" viewBox="0 0 20 20" aria-hidden="true">
              <path d="m7 4.8 8 5.2-8 5.2z" fill="currentColor" />
            </svg>
            <svg v-else viewBox="0 0 20 20" aria-hidden="true">
              <path d="M6.2 4.8h2.5v10.4H6.2zm5.1 0h2.5v10.4h-2.5z" fill="currentColor" />
            </svg>
          </button>
          <button class="btn-ghost" :disabled="saving" @click="close">
            {{ cancelAsk ? '确认放弃修改？' : '取消' }}
          </button>
          <button class="save-btn" :disabled="!canSave" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </header>

      <!-- 缩放 + 网格工具栏 -->
      <div class="ws-toolbar">
        <button class="t-btn" title="适配整首歌曲" @click="computeFit">适配</button>
        <button class="t-btn" title="缩小" @click="zoomBy(1 / 1.5)">−</button>
        <input
          v-model.number="pxPerSec"
          type="range"
          class="zoom-slider"
          min="2"
          max="900"
          step="1"
          title="水平缩放"
        />
        <button class="t-btn" title="放大" @click="zoomBy(1.5)">＋</button>
        <span class="zoom-val mono">{{ Math.round(pxPerSec) }} px/s</span>
        <span class="tb-sep"></span>
        <div class="seg">
          <button
            v-for="o in DENSITY_OPTIONS"
            :key="o.value"
            :class="{ on: density === o.value }"
            @click="density = o.value"
          >{{ o.label }}</button>
        </div>
        <label class="bpb">
          <span class="caption">每小节</span>
          <select v-model.number="beatsPerBar" class="bpb-select mono">
            <option v-for="n in 12" :key="n" :value="n">{{ n }} 拍</option>
          </select>
        </label>
        <button class="switch" :class="{ on: snapOn }" role="switch" :aria-pressed="snapOn" @click="snapOn = !snapOn">
          <span class="switch-knob"></span>
        </button>
        <span class="caption">吸附</span>
        <span class="tb-hint caption">拖动空白/刻度尺=平移 · 滚轮缩放(⌘/Ctrl+滚轮) · 拖边缘=改边界 · 拖中部=平移段 · 双击=分割 · Del=删除</span>
      </div>

      <!-- 编曲视图 -->
      <div ref="viewportRef" class="arrange" :class="{ panning }" @scroll="scrollLeft = $event.target.scrollLeft" @wheel.prevent="onCanvasWheel">
        <div class="canvas" :style="{ width: contentW + 'px' }">
          <!-- 网格线（背景层） -->
          <template v-for="(l, i) in gridRender.lines" :key="'g' + i">
            <div
              class="gline"
              :class="l.kind"
              :style="{ left: l.x + 'px' }"
            ></div>
          </template>

          <!-- 刻度尺：小节号 + 秒刻度 -->
          <div class="ruler" @pointerdown="startPan" @click="onTimelineClick">
            <span
              v-for="(b, i) in gridRender.barNo"
              :key="'b' + i"
              class="ruler-bar mono"
              :style="{ left: b.x + 'px' }"
            >{{ b.label }}</span>
            <span
              v-for="(s, i) in gridRender.secTicks"
              :key="'s' + i"
              class="ruler-sec mono"
              :style="{ left: s.x + 'px' }"
            >{{ s.label }}</span>
          </div>

          <!-- 音轨泳道 -->
          <div
            class="lane"
            @pointerdown="onLaneDown"
            @pointermove="onLaneMove"
            @pointerup="onLaneUp"
            @pointercancel="onLaneUp"
            @dblclick="onLaneDbl"
            @click="onTimelineClick"
          >
            <div class="preview-cursor" :style="{ left: previewCursor + 'px' }"></div>
            <div
              v-for="b in blockGeom"
              :key="rows[b.idx].uid"
              class="block"
              :class="{
                sel: sel === b.idx,
                noise: (rows[b.idx].chord || 'N').trim() === 'N',
                bad: sel === b.idx && invalidSel,
              }"
              :style="{ left: b.x0 + 'px', width: Math.max(b.w, 1) + 'px' }"
            >
              <span v-if="b.w > 30" class="block-name mono">{{ rows[b.idx].chord || 'N' }}</span>
            </div>
            <!-- 拖动预览线 -->
            <div
              v-if="dragPreview"
              class="drag-ghost"
              :style="{
                left: Math.min(dragPreview.t0, dragPreview.t1) * px() + 'px',
                width: Math.abs(dragPreview.t1 - dragPreview.t0) * px() + 'px',
              }"
            ></div>
          </div>
        </div>
      </div>

      <!-- 检查器 -->
      <div class="inspector">
        <template v-if="selRow">
          <span class="caption">选中块</span>
          <input
            v-model="selRow.chord"
            class="ins-name mono"
            :class="{ bad: invalidSel }"
            spellcheck="false"
            placeholder="和弦名或 N"
            @input="markDirty()"
          />
          <span class="ins-status">{{ invalidSel ? '✗ 无法识别' : '✓' }}</span>
          <span class="ins-sep"></span>
          <button class="i-btn" title="起点前移 0.1s" @click="nudgeStart(-0.1)">−</button>
          <span class="ins-ts mono" :title="fmt10(selRow.timestamp)">{{ fmt10(selRow.timestamp) }}</span>
          <button class="i-btn" title="起点后移 0.1s" @click="nudgeStart(0.1)">＋</button>
          <span class="ins-sep"></span>
          <span class="ins-dur caption">时长 {{ fmtDur(selRow.timestamp, (blockGeom[sel] && blockGeom[sel].t1) || duration) }}</span>
          <span class="ins-sep"></span>
          <button class="ins-act" @click="splitBlock(sel, (blockGeom[sel].t0 + blockGeom[sel].t1) / 2)">分割</button>
          <button class="ins-act danger" @click="removeBlock(sel)">删除</button>
        </template>
        <template v-else>
          <span class="caption">点击选择一个和弦块开始编辑</span>
        </template>
        <span class="ins-spacer"></span>
        <span v-if="anyInvalid.length" class="ins-error">
          第 {{ anyInvalid.join('、') }} 处和弦名无法识别，修正后再保存
        </span>
        <span v-if="saveError" class="ins-error">{{ saveError }}</span>
      </div>

      <!-- 键盘预览 -->
      <footer class="ws-preview">
        <div class="preview-meta">
          <span class="caption">构成音预览</span>
          <span v-if="selParsed" class="preview-name mono">{{ selRow.chord.trim() }}</span>
          <span v-else class="caption bpm-none">选中「有效和弦」后在此显示构成音</span>
        </div>
        <PianoKeyboard v-if="previewHighlight" :highlight="previewHighlight" />
      </footer>
    </div>
  </div>
</template>

<style scoped>
.ws-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(6, 7, 9, 0.7);
  backdrop-filter: blur(4px);
  display: grid;
  place-items: center;
  padding: 24px;
}
.ws-panel {
  width: min(1240px, 100%);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  animation: wsin 0.2s ease both;
}
@keyframes wsin {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.ws-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-soft);
}
.ws-title-box {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}
.ws-title {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 500;
  letter-spacing: 0.1em;
  white-space: nowrap;
}
.ws-file {
  font-size: 12px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}
.ws-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}
.ws-audio {
  display: none;
}
.ws-preview-time {
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}
.ws-play {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--text-dim);
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}
.ws-play svg {
  width: 14px;
  height: 14px;
}
.ws-play:hover {
  color: var(--accent);
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.bpm-chip {
  font-size: 12px;
  color: var(--accent);
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  border-radius: 999px;
  padding: 3px 12px;
  letter-spacing: 0.06em;
}
.bpm-none {
  color: var(--text-faint);
}
.bpm-loading {
  color: var(--text-dim);
}
.save-btn {
  padding: 8px 22px;
  border-radius: 999px;
  font-size: 13px;
  letter-spacing: 0.1em;
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  color: var(--accent);
  transition: background 0.2s ease, color 0.2s ease, opacity 0.2s ease;
}
.save-btn:hover:not(:disabled) {
  background: var(--accent);
  color: #211c12;
}
.save-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.ws-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border-soft);
  flex-wrap: wrap;
}
.t-btn {
  min-width: 26px;
  height: 24px;
  border: 1px solid var(--border);
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  padding: 0 8px;
  color: var(--text-dim);
}
.t-btn:hover {
  color: var(--accent);
  border-color: var(--accent-line);
}
.zoom-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 150px;
  height: 2px;
  border-radius: 1px;
  background: var(--border);
  outline: none;
  cursor: pointer;
}
.zoom-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--accent);
}
.zoom-val {
  font-size: 10.5px;
  color: var(--text-faint);
  min-width: 52px;
}
.tb-sep {
  width: 1px;
  height: 16px;
  background: var(--border-soft);
  margin: 0 4px;
}
.bpb {
  display: flex;
  align-items: center;
  gap: 5px;
}
.bpb-select {
  background: var(--surface-2);
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 11.5px;
  padding: 2px 6px;
  outline: none;
}
.switch {
  position: relative;
  width: 32px;
  height: 18px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  transition: border-color 0.25s ease, background 0.25s ease;
  flex: none;
}
.switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--text-faint);
  transition: left 0.25s ease, background 0.25s ease;
}
.switch.on {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.switch.on .switch-knob {
  left: 16px;
  background: var(--accent);
}
.tb-hint {
  margin-left: auto;
  color: var(--text-faint);
  letter-spacing: 0.02em;
}

/* 编曲视图 */
.arrange {
  flex: 1;
  min-height: 220px;
  overflow: auto;
  position: relative;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.012), transparent 40%),
    var(--bg-soft);
  touch-action: none;
  user-select: none;
}
.arrange.panning,
.arrange.panning * {
  cursor: grabbing !important;
}
.canvas {
  position: relative;
  min-width: 100%;
  height: 144px;
}
.gline {
  position: absolute;
  top: 34px;
  bottom: 0;
  width: 1px;
  background: rgba(154, 158, 168, 0.09);
  pointer-events: none;
}
.gline.beat {
  background: rgba(154, 158, 168, 0.14);
}
.gline.bar {
  width: 1.5px;
  background: rgba(194, 171, 127, 0.32);
}
.gline.eighth,
.gline.sixteenth {
  background: rgba(154, 158, 168, 0.05);
}

.ruler {
  position: relative;
  height: 34px;
  border-bottom: 1px solid var(--border-soft);
  background: var(--surface-2);
  overflow: hidden;
  cursor: grab;
}
.ruler-bar {
  position: absolute;
  top: 2px;
  transform: translateX(3px);
  font-size: 10px;
  color: var(--accent);
  letter-spacing: 0.04em;
}
.ruler-sec {
  position: absolute;
  top: 20px;
  transform: translateX(3px);
  font-size: 9.5px;
  color: var(--text-faint);
}

.lane {
  position: relative;
  height: 110px;
  cursor: grab;
}
.preview-cursor {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-line);
  pointer-events: none;
  z-index: 10;
  transition: left 0.08s linear;
}

.block {
  position: absolute;
  top: 12px;
  height: 62px;
  border-radius: 6px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--text-faint);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: move;
  transition: border-color 0.12s ease, background 0.12s ease;
}
.block.sel {
  background: var(--accent-soft);
  border-color: var(--accent);
  border-left-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-line);
}
.block.noise {
  border-left-style: dashed;
  opacity: 0.55;
}
.block.bad {
  border-color: var(--danger);
}
.block-name {
  font-size: 12.5px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 6px;
  max-width: 100%;
}
.block.sel .block-name {
  color: var(--text);
}
.block.sel::before,
.block.sel::after {
  content: '';
  position: absolute;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--accent-line);
  pointer-events: none;
}
.block.sel::before {
  left: 0;
}
.block.sel::after {
  right: 0;
}
.drag-ghost {
  position: absolute;
  top: 0;
  height: 110px;
  background: rgba(194, 171, 127, 0.18);
  border: 1px dashed var(--accent-line);
  pointer-events: none;
  z-index: 5;
}

/* 检查器 */
.inspector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-top: 1px solid var(--border-soft);
  background: var(--surface-2);
  flex-wrap: wrap;
}
.ins-name {
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 14px;
  width: 130px;
  outline: none;
  padding: 2px 4px;
  letter-spacing: 0.04em;
}
.ins-name:focus {
  border-bottom-color: var(--accent-line);
}
.ins-name.bad {
  border-bottom-color: var(--danger);
  color: var(--danger);
}
.ins-status {
  font-size: 13px;
  color: var(--accent);
  width: 14px;
}
.ins-ts {
  font-size: 12.5px;
  color: var(--text-dim);
  min-width: 52px;
  text-align: center;
}
.ins-dur {
  color: var(--text-faint);
}
.ins-sep {
  width: 1px;
  height: 16px;
  background: var(--border-soft);
  margin: 0 2px;
}
.i-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--border);
  display: grid;
  place-items: center;
  font-size: 13px;
  line-height: 1;
  color: var(--text-dim);
  flex: none;
}
.i-btn:hover {
  color: var(--accent);
  border-color: var(--accent-line);
}
.ins-act {
  font-size: 11.5px;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 14px;
  transition: color 0.2s ease, border-color 0.2s ease;
}
.ins-act:hover {
  color: var(--accent);
  border-color: var(--accent-line);
}
.ins-act.danger:hover {
  color: var(--danger);
  border-color: rgba(201, 123, 109, 0.45);
}
.ins-spacer {
  flex: 1;
}
.ins-error {
  font-size: 12px;
  color: var(--danger);
  letter-spacing: 0.03em;
}

.ws-preview {
  border-top: 1px solid var(--border-soft);
  padding: 8px 20px 14px;
}
.preview-meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 2px;
}
.preview-name {
  font-size: 12px;
  color: var(--accent);
  letter-spacing: 0.04em;
}
</style>
