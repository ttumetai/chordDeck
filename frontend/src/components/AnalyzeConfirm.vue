<script setup>
import { ref } from 'vue'

const props = defineProps({
  file: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  cachedResult: { type: Object, default: null },
})

const emit = defineEmits(['confirm', 'cancel', 'open-cache', 'reanalyze-cache'])

const filename = ref(props.file.name)
const engine = ref('auto')
const engines = [
  { value: 'auto', label: '自动', detail: '综合推荐 · 失败时自动回退' },
  { value: 'deepchroma', label: 'DeepChroma', detail: '精度优先 · 适合大多数歌曲' },
  { value: 'chordino', label: 'Chordino', detail: '速度较快 · 传统稳定方案' },
  { value: 'lv-chordia', label: 'LV-Chordia', detail: '复杂和弦优先 · 内存占用较高' },
]

function confirm() {
  emit('confirm', { filename: filename.value.trim() || props.file.name, engine: engine.value })
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
        <label class="analysis-field">
          <span>文件名</span>
          <input v-model="filename" type="text" maxlength="240" :disabled="busy" />
        </label>

        <fieldset class="analysis-field engine-field">
          <legend>识别模型</legend>
          <div class="engine-options" role="radiogroup" aria-label="识别模型">
            <label
              v-for="item in engines"
              :key="item.value"
              class="engine-option"
              :class="{ selected: engine === item.value }"
            >
              <input v-model="engine" type="radio" name="analysis-engine" :value="item.value" :disabled="busy" />
              <span class="engine-copy">
                <strong>{{ item.label }}</strong>
                <small>{{ item.detail }}</small>
              </span>
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

.analysis-field input[type='text'] {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  outline: none;
  background: var(--bg-soft);
  color: var(--text);
  font: inherit;
}

.analysis-field input[type='text']:focus {
  border-color: var(--accent-line);
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
  color: var(--text-faint);
  font-size: 11px;
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
  .engine-options { grid-template-columns: 1fr; }
  .cache-actions { flex-wrap: wrap; }
  .cache-actions .analysis-primary { flex: 1 0 100%; }
}
</style>
