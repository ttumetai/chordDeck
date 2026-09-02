<script setup>
defineProps({
  title: { type: String, default: '确认' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  danger: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <div class="confirm-overlay" @click.self="emit('cancel')">
    <div class="confirm-panel">
      <h3 class="confirm-title">{{ title }}</h3>
      <p class="confirm-msg">{{ message }}</p>
      <div class="confirm-actions">
        <button class="btn-ghost" @click="emit('cancel')">取消</button>
        <button
          class="confirm-ok"
          :class="{ danger }"
          @click="emit('confirm')"
        >{{ confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(6, 7, 9, 0.6);
  backdrop-filter: blur(3px);
  display: grid;
  place-items: center;
}
.confirm-panel {
  width: min(380px, calc(100vw - 48px));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 26px 26px 20px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.5);
  animation: cpop 0.18s ease both;
}
@keyframes cpop {
  from {
    opacity: 0;
    transform: scale(0.97) translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.confirm-title {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--text);
}
.confirm-msg {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-dim);
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 22px;
}
.confirm-ok {
  padding: 9px 20px;
  border-radius: 999px;
  font-size: 13px;
  letter-spacing: 0.08em;
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  color: var(--accent);
  transition: background 0.2s ease, color 0.2s ease;
}
.confirm-ok:hover {
  background: var(--accent);
  color: #211c12;
}
.confirm-ok.danger {
  border-color: rgba(201, 123, 109, 0.5);
  background: rgba(201, 123, 109, 0.1);
  color: var(--danger);
}
.confirm-ok.danger:hover {
  background: var(--danger);
  color: #fff;
}
</style>
