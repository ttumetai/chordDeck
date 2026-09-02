// 极简事件总线：跨组件解耦（如"打开编辑器时暂停播放"）
const listeners = new Map()

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set())
  listeners.get(event).add(fn)
  return () => off(event, fn)
}

export function off(event, fn) {
  listeners.get(event)?.delete(fn)
}

export function emit(event, ...args) {
  listeners.get(event)?.forEach((fn) => {
    try {
      fn(...args)
    } catch {
      /* ignore listener errors */
    }
  })
}

export const bus = { on, off, emit }
