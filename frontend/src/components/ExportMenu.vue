<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import {
  baseName,
  buildChordChart,
  buildCsv,
  buildJson,
  saveFile,
} from '../lib/export'

const props = defineProps({
  chords: { type: Array, required: true },
  filename: { type: String, default: '' },
  duration: { type: Number, default: 0 },
  source: { type: String, default: '' },
})

const open = ref(false)
const rootRef = ref(null)

function toggle() {
  open.value = !open.value
}

function payload() {
  return {
    filename: props.filename,
    duration: props.duration,
    source: props.source,
    chords: props.chords,
  }
}

async function exportCsv() {
  open.value = false
  await saveFile(
    `${baseName(props.filename)}.chords.csv`,
    buildCsv(props.chords),
    'text/csv',
  )
}

async function exportJson() {
  open.value = false
  await saveFile(
    `${baseName(props.filename)}.chords.json`,
    buildJson(payload()),
    'application/json',
  )
}

async function exportTxt() {
  open.value = false
  await saveFile(
    `${baseName(props.filename)}.chords.txt`,
    buildChordChart(payload()),
    'text/plain',
  )
}

function onDocPointerDown(e) {
  if (!rootRef.value?.contains(e.target)) open.value = false
}
function onKeydown(e) {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocPointerDown)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocPointerDown)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="rootRef" class="export">
    <button
      class="btn-ghost export-btn"
      :class="{ open }"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggle"
    >
      <svg class="i-download" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path
          d="M10 3v8m0 0 3-3m-3 3L7 8"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M4 13.5v1.6A1.9 1.9 0 0 0 5.9 17h8.2a1.9 1.9 0 0 0 1.9-1.9v-1.6"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
        />
      </svg>
      <span>导出和弦</span>
      <svg
        class="i-chevron"
        viewBox="0 0 20 20"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="m6 8 4 4 4-4"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <transition name="pop">
      <div v-if="open" class="menu" role="menu">
        <button class="item" role="menuitem" @click="exportCsv">
          <span class="item-name">CSV</span>
          <span class="item-desc">表格 / Excel 兼容</span>
        </button>
        <button class="item" role="menuitem" @click="exportJson">
          <span class="item-name">JSON</span>
          <span class="item-desc">完整原始数据</span>
        </button>
        <button class="item" role="menuitem" @click="exportTxt">
          <span class="item-name">和弦谱</span>
          <span class="item-desc">文本 · 时间 + 和弦</span>
        </button>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.export {
  position: relative;
}

.export-btn .i-download {
  width: 15px;
  height: 15px;
}
.export-btn .i-chevron {
  width: 12px;
  height: 12px;
  color: var(--text-faint);
  transition: transform 0.25s ease;
}
.export-btn.open .i-chevron {
  transform: rotate(180deg);
}

.menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 208px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.45);
  z-index: 20;
}

.item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 7px;
  text-align: left;
  transition: background 0.2s ease;
}
.item:hover {
  background: var(--accent-soft);
}

.item-name {
  font-family: var(--font-mono);
  font-size: 13px;
  letter-spacing: 0.05em;
  color: var(--text);
  min-width: 58px;
}
.item-desc {
  font-size: 11.5px;
  color: var(--text-faint);
  letter-spacing: 0.05em;
}

/* 下拉展开动画 */
.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
