<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  file: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  cachedResult: { type: Object, default: null },
  capabilities: { type: Object, default: () => ({}) },
  recommendedEngine: { type: String, default: 'auto' },
})

const emit = defineEmits(['confirm', 'cancel', 'reselect', 'open-cache', 'reanalyze-cache'])

const engines = [
  { value: 'auto', label: '自动', detail: '综合推荐 · 失败时自动回退' },
  { value: 'deepchroma', label: 'DeepChroma', detail: '精度优先 · 适合大多数歌曲' },
  { value: 'chordino', label: 'Chordino', detail: '速度较快 · 传统稳定方案' },
  { value: 'lv-chordia', label: 'LV-Chordia', detail: '复杂和弦优先 · 内存占用较高' },
]

const engine = ref('auto')

watch(
  () => props.recommendedEngine,
  (value) => {
    if (value && engine.value === 'auto') engine.value = value
  },
  { immediate: true },
)

function statusFor(value) {
  return props.capabilities?.engines?.[value] || null
}

function isAvailable(value) {
  return statusFor(value)?.available !== false
}

function engineDetail(item) {
  const status = statusFor(item.value)
  return isAvailable(item.value)
    ? item.detail
    : `当前系统不支持 · ${status?.reason || '依赖不可用'}`
}

function isRecommended(value) {
  return value === props.recommendedEngine && isAvailable(value)
}

function confirm() {
  emit('confirm', { engine: engine.value })
}
</script>

<template>
  <div class="analysis-overlay" @click.self="!busy && emit('cancel')">
    <section class="analysis-panel" role="dialog" aria-modal="true" aria-labelledby="analysis-title">
      <p class="analysis-kicker">准备分析</p>
      <h2 id="analysis-title" class="analysis-title">
        {{ cachedResult ? '发现本地缓存' : '确认分析设置' }}
      </h2>

      <template v-if="cachedResult">
        <p class="analysis-message">
          「{{ cachedResult.filename }}」已有 {{ cachedResult.engine }} 引擎的分析结果。
        </p>
        <div class="cache-summary">
          <span>缓存结果</span>
          <strong>{{ cachedResult.chords?.length || 0 }} 处和弦变化</strong>
        </div>
        <div class="analysis-actions cache-actions">
          <button class="btn-ghost" :disabled="busy" @click="emit('cancel')">返回修改</button>
          <button class="btn-ghost" :disabled="busy" @click="emit('reanalyze-cache')">重新分析</button>
          <button class="analysis-primary" :disabled="busy" @click="emit('open-cache')">直接打开</button>
        </div>
      </template>

      <template v-else>
        <div class="analysis-field file-field">
          <span>音频文件</span>
          <div class="file-row">
            <div class="file-info">
              <svg class="file-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M5 2.8h6.2L15 6.6v10.6H5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round" />
                <path d="M11 2.8v4h4M7.5 10h5M7.5 13h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
              </svg>
              <strong :title="file.name">{{ file.name }}</strong>
            </div>
            <button class="file-reselect" :disabled="busy" @click="emit('reselect')">
              重新选择文件
            </button>
          </div>
        </div>

        <fieldset class="analysis-field engine-field">
          <legend>识别模型</legend>
          <div class="engine-options" role="radiogroup" aria-label="识别模型">
            <label
              v-for="item in engines"
              :key="item.value"
              class="engine-option"
              :class="{ selected: engine === item.value, unavailable: !isAvailable(item.value), recommended: isRecommended(item.value) }"
              :title="engineDetail(item)"
            >
              <input v-model="engine" type="radio" name="analysis-engine" :value="item.value" :disabled="busy || !isAvailable(item.value)" />
              <span class="engine-copy">
                <strong>{{ item.label }}</strong>
                <small>{{ engineDetail(item) }}</small>
              </span>
              <span v-if="isRecommended(item.value)" class="engine-recommended">推荐</span>
              <span class="engine-mark" aria-hidden="true"></span>
            </label>
          </div>
        </fieldset>

        <p v-if="busy" class="analysis-status">正在上传并检查本地缓存…</p>
        <div class="analysis-actions">
          <button class="btn-ghost" :disabled="busy" @click="emit('cancel')">取消</button>
          <button class="analysis-primary" :disabled="busy" @click="confirm">
            {{ busy ? '正在检查…' : '确认并开始分析' }}
          </button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.analysis-overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(6, 7, 9, 0.72);
  backdrop-filter: blur(5px);
}

.analysis-panel {
  width: min(520px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  padding: 30px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.5);
  animation: analysis-pop 0.18s ease both;
}

@keyframes analysis-pop {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to { opacity: 1; transform: none; }
}

.analysis-kicker {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.analysis-title {
  margin-top: 8px;
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 0.08em;
}

.analysis-message {
  margin-top: 14px;
  color: var(--text-dim);
  font-size: 13px;
}

.analysis-field {
  display: block;
  margin-top: 24px;
  border: 0;
}

.analysis-field > span,
.analysis-field legend {
  display: block;
  margin-bottom: 8px;
  color: var(--text-faint);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-soft);
}

.file-info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: var(--text);
}

.file-icon {
  flex: none;
  width: 18px;
  height: 18px;
  color: var(--accent);
}

.file-info strong {
  overflow: hidden;
  font-size: 14px;
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-reselect {
  flex: none;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 12px;
  white-space: nowrap;
}

.file-reselect:hover:not(:disabled) {
  border-color: var(--accent-line);
  color: var(--accent);
}

.engine-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.engine-option {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.engine-option:hover,
.engine-option.selected {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}

.engine-option.recommended {
  border-color: var(--accent-line);
}

.engine-option.recommended .engine-copy strong {
  color: var(--accent);
}

.engine-option.unavailable {
  cursor: not-allowed;
  opacity: 0.45;
}

.engine-option.unavailable:hover {
  border-color: var(--border);
  background: transparent;
}

.engine-option input {
  accent-color: var(--accent);
}

.engine-copy {
  display: grid;
  min-width: 0;
}

.engine-copy strong {
  overflow: hidden;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.engine-copy small {
  overflow: hidden;
  color: var(--text-faint);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.engine-recommended {
  flex: none;
  padding: 2px 6px;
  border: 1px solid var(--accent-line);
  border-radius: 999px;
  color: var(--accent);
  font-size: 10px;
}

.engine-mark {
  width: 7px;
  height: 7px;
  margin-left: auto;
  border-radius: 50%;
  background: transparent;
}

.engine-option.selected .engine-mark {
  background: var(--accent);
}

.cache-summary {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 22px;
  padding: 12px 0;
  border-top: 1px solid var(--border-soft);
  border-bottom: 1px solid var(--border-soft);
  color: var(--text-faint);
  font-size: 12px;
}

.cache-summary strong {
  color: var(--text-dim);
  font-weight: 400;
}

.analysis-status {
  margin-top: 18px;
  color: var(--accent);
  font-size: 12px;
}

.analysis-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 26px;
}

.analysis-primary {
  padding: 9px 18px;
  border: 1px solid var(--accent-line);
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 13px;
}

.analysis-primary:hover:not(:disabled) {
  background: var(--accent);
  color: #211c12;
}

button:disabled {
  cursor: wait;
  opacity: 0.55;
}

@media (max-width: 520px) {
  .analysis-panel { padding: 24px 20px; }
  .file-row { align-items: flex-start; flex-direction: column; }
  .file-reselect { align-self: flex-end; }
  .engine-options { grid-template-columns: 1fr; }
  .cache-actions { flex-wrap: wrap; }
  .cache-actions .analysis-primary { flex: 1 0 100%; }
}
</style>
