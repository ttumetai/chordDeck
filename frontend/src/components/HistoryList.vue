<script setup>
import { onUnmounted, ref } from 'vue'

defineProps({
  items: { type: Array, required: true },
  busyId: { type: String, default: '' }, // 正在重新识别的记录 id
})
const emit = defineEmits(['open', 'delete', 'reanalyze'])

// 两段式删除确认：第一次点击进入「确认删除」，再次点击才真正删除
const confirmId = ref('')
let confirmTimer = null

function resetConfirm() {
  confirmId.value = ''
  clearTimeout(confirmTimer)
}

function askDelete(it) {
  if (confirmId.value === it.id) {
    emit('delete', it)
    resetConfirm()
  } else {
    confirmId.value = it.id
    clearTimeout(confirmTimer)
    confirmTimer = setTimeout(resetConfirm, 2600)
  }
}

function onOpen(it) {
  if (confirmId.value === it.id) {
    resetConfirm()
    return
  }
  emit('open', it)
}

onUnmounted(resetConfirm)

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(String(s).replace(' ', 'T') + 'Z')
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function fmtDur(t) {
  if (!Number.isFinite(t) || t <= 0) return '—'
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const sourceLabel = (s) =>
  s === 'deepchroma' ? 'DeepChroma' : s === 'chordino' ? 'Chordino' : '模板匹配'
</script>

<template>
  <div class="history fade-in">
    <div class="history-head">
      <span class="caption">历史记录</span>
      <span class="history-count">{{ items.length }} 条</span>
    </div>
    <ul class="history-list">
      <li v-for="it in items" :key="it.id" class="history-item" @click="onOpen(it)">
        <div class="h-main">
          <span class="h-file" :title="it.filename">{{ it.filename }}</span>
          <span class="h-actions">
            <button
              class="h-btn"
              :disabled="busyId === it.id"
              :title="'用已保存的音频重新识别：' + it.filename"
              @click.stop="emit('reanalyze', it)"
            >
              <svg
                v-if="busyId === it.id"
                class="h-spin"
                viewBox="0 0 20 20"
                aria-hidden="true"
              >
                <path
                  d="M10 2.6a7.4 7.4 0 1 0 7.4 7.4"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                />
              </svg>
              <svg v-else class="h-ico" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path
                  d="M16.2 7.2A6.8 6.8 0 1 0 17 10.4"
                  stroke="currentColor"
                  stroke-width="1.3"
                  stroke-linecap="round"
                />
                <path
                  d="M16.2 3.4v3.8h-3.8"
                  stroke="currentColor"
                  stroke-width="1.3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              {{ busyId === it.id ? '识别中' : '重新识别' }}
            </button>
            <button
              class="h-btn danger"
              :class="{ confirm: confirmId === it.id }"
              :title="'删除记录及其音频缓存：' + it.filename"
              @click.stop="askDelete(it)"
            >
              {{ confirmId === it.id ? '确认删除' : '删除' }}
            </button>
          </span>
        </div>
        <div class="h-meta">
          <span>{{ fmtDate(it.created_at) }}</span>
          <span class="h-sep"></span>
          <span>{{ fmtDur(it.duration) }}</span>
          <span class="h-sep"></span>
          <span>{{ it.chords_count }} 处和弦</span>
          <span class="h-engine">{{ sourceLabel(it.source) }}</span>
          <span v-if="it.edited" class="h-edited" title="已人工编辑过">已编辑</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.history {
  margin-top: 40px;
}

.history-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.history-count {
  font-size: 11px;
  color: var(--text-faint);
}

.history-list {
  list-style: none;
  border-top: 1px solid var(--border-soft);
}

.history-item {
  padding: 13px 14px;
  border-bottom: 1px solid var(--border-soft);
  cursor: pointer;
  transition: background 0.22s ease;
}
.history-item:hover {
  background: var(--surface);
}

.h-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.h-file {
  flex: 1;
  min-width: 0;
  font-size: 13.5px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.h-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.h-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 11px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  font-size: 11.5px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  transition: color 0.22s ease, border-color 0.22s ease, background 0.22s ease;
}
.h-btn:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.h-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.h-btn.danger:hover:not(:disabled) {
  color: var(--danger);
  border-color: rgba(201, 123, 109, 0.4);
  background: rgba(201, 123, 109, 0.08);
}
.h-btn.danger.confirm {
  color: var(--danger);
  border-color: rgba(201, 123, 109, 0.45);
  background: rgba(201, 123, 109, 0.1);
}

.h-ico {
  width: 12px;
  height: 12px;
}
.h-spin {
  width: 12px;
  height: 12px;
  animation: hSpin 0.9s linear infinite;
}
@keyframes hSpin {
  to {
    transform: rotate(360deg);
  }
}

.h-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--text-faint);
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.h-sep {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--border);
  flex: none;
}

.h-engine {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  padding: 2px 8px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
}

.h-edited {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  color: var(--accent);
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  border-radius: 999px;
  padding: 2px 8px;
}
</style>
