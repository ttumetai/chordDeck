<script setup>
import { ref } from 'vue'

const emit = defineEmits(['select'])

const ALLOWED = [
  'wav', 'mp3', 'ogg', 'flac', 'm4a', 'aac', 'webm', 'opus', 'aiff',
]
const ALLOWED_RE = new RegExp(`\\.(${ALLOWED.join('|')})$`, 'i')

const dragging = ref(false)
const invalidMsg = ref('')
const inputRef = ref(null)

defineExpose({ pick })

function pick() {
  inputRef.value?.click()
}

function onInputChange(e) {
  const file = e.target.files?.[0]
  if (file) accept(file)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) accept(file)
}

function accept(file) {
  if (!file.type.startsWith('audio/') && !ALLOWED_RE.test(file.name)) {
    invalidMsg.value = `「${file.name}」不是受支持的音频文件`
    return
  }
  invalidMsg.value = ''
  emit('select', file)
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div
    class="zone"
    :class="{ dragging }"
    role="button"
    tabindex="0"
    @click="pick"
    @keydown.enter="pick"
    @keydown.space.prevent="pick"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
  >
    <svg class="zone-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 17V6.6m0 0 3.2 3.2M9 6.6 5.8 9.8"
        stroke="currentColor"
        stroke-width="1.1"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M4 17.4v1.1A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5v-1.1"
        stroke="currentColor"
        stroke-width="1.1"
        stroke-linecap="round"
      />
    </svg>
    <p class="zone-title">选择或拖入音频文件</p>
    <p class="zone-sub">
      支持 wav · mp3 · ogg · flac · m4a · aac · webm · opus，单文件不超过 200 MB
    </p>
    <span class="zone-hint">点击选择文件</span>

    <p v-if="invalidMsg" class="zone-invalid">{{ invalidMsg }}</p>

    <input
      ref="inputRef"
      type="file"
      accept="audio/*,.wav,.mp3,.ogg,.flac,.m4a,.aac,.webm,.opus,.aiff,.aif"
      class="zone-input"
      @change="onInputChange"
    />
  </div>
</template>

<style scoped>
.zone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 72px 32px;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.014),
    rgba(255, 255, 255, 0)
  );
  cursor: pointer;
  outline: none;
  transition: border-color 0.3s ease, background 0.3s ease,
    box-shadow 0.3s ease;
  user-select: none;
}

.zone:hover,
.zone:focus-visible {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}

.zone.dragging {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}

.zone-icon {
  width: 34px;
  height: 34px;
  color: var(--text-dim);
  margin-bottom: 8px;
  transition: color 0.3s ease, transform 0.3s ease;
}
.zone:hover .zone-icon,
.zone.dragging .zone-icon {
  color: var(--accent);
  transform: translateY(-2px);
}

.zone-title {
  font-family: var(--font-serif);
  font-size: 19px;
  letter-spacing: 0.1em;
  color: var(--text);
}

.zone-sub {
  font-size: 12.5px;
  color: var(--text-faint);
  letter-spacing: 0.04em;
}

.zone-hint {
  margin-top: 14px;
  padding: 7px 20px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 0.14em;
  color: var(--text-dim);
  transition: color 0.3s ease, border-color 0.3s ease;
}
.zone:hover .zone-hint,
.zone.dragging .zone-hint {
  color: var(--accent);
  border-color: var(--accent-line);
}

.zone-invalid {
  margin-top: 6px;
  font-size: 12px;
  color: var(--danger);
  letter-spacing: 0.04em;
}

.zone-input {
  display: none;
}
</style>
