// 钢琴音频引擎：真实采样优先（frontend/public/samples，C3–B4），
// 缺失/加载失败时回退 Web Audio 振荡器合成；支持总增益与抢占式重触发。
// 移植自 chordE (audio.ts) 并改进：采样缓存、并发预取、主动 stop。

import { midiToNoteName } from './music.js'

const SAMPLE_BASE = '/samples'

function toSampleFileName(noteName) {
  return noteName.replace('#', 's')
}

class PianoEngine {
  constructor() {
    this.ctx = null
    this.masterGain = null
    this.enabled = true // 由外部开关控制（R2）
    this.volume = 0.5 // 0..1（R3）
    this.sampleCache = new Map()
    this.active = new Set() // 正在发声的源（供 stop 抢占）
  }

  /* ── 生命周期 ── */

  ensureCtx() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext
      if (!Ctx) return null
      this.ctx = new Ctx()
      this.masterGain = this.ctx.createGain()
      this.masterGain.gain.value = this.volume * 0.5
      this.masterGain.connect(this.ctx.destination)
    }
    return this.ctx
  }

  /** 在用户手势内调用以解锁自动播放策略 */
  async unlock() {
    const ctx = this.ensureCtx()
    if (ctx && ctx.state === 'suspended') {
      try {
        await ctx.resume()
      } catch {
        /* ignore */
      }
    }
  }

  setVolume(v) {
    this.volume = Math.min(1, Math.max(0, v))
    if (this.masterGain && this.ctx) {
      this.masterGain.gain.setTargetAtTime(this.volume * 0.5, this.ctx.currentTime, 0.02)
    }
  }

  /** 抢占：快速收掉当前所有发声的音符（换和弦时不糊） */
  stop() {
    if (!this.ctx) return
    const now = this.ctx.currentTime
    for (const node of this.active) {
      try {
        node.gain.cancelScheduledValues(now)
        node.gain.setTargetAtTime(0.0001, now, 0.05)
      } catch {
        /* ignore */
      }
      try {
        node.source.stop(now + 0.4)
      } catch {
        /* ignore */
      }
    }
    this.active.clear()
  }

  release() {
    this.stop()
    if (this.ctx) {
      this.ctx.close().catch(() => {})
      this.ctx = null
      this.masterGain = null
    }
  }

  /* ── 发声 ── */

  /** 和弦齐奏；enabled=false 或 midi 为空时静默 */
  async playChord(midis) {
    if (!this.enabled || !midis?.length) return
    await this.unlock()
    if (!this.ctx) return
    this.stop() // 抢占上一和弦
    midis.forEach((m) => {
      void this.playMidi(m)
    })
  }

  async playMidi(midi) {
    if (!this.ctx) return
    const noteName = midiToNoteName(midi)
    const played = await this.tryPlaySample(noteName)
    if (!played) this.playOscillator(midi)
  }

  /* ── 采样（缓存 + 解码） ── */

  async loadSample(noteName) {
    if (this.sampleCache.has(noteName)) return this.sampleCache.get(noteName)
    const promise = (async () => {
      const ctx = this.ensureCtx()
      const resp = await fetch(`${SAMPLE_BASE}/${toSampleFileName(noteName)}.mp3`).catch(() => null)
      if (!resp?.ok) return null
      const buf = await resp.arrayBuffer()
      const decoded = await ctx.decodeAudioData(buf).catch(() => null)
      return decoded
    })()
    this.sampleCache.set(noteName, promise)
    return promise
  }

  async tryPlaySample(noteName) {
    const buffer = await this.loadSample(noteName)
    if (!buffer || !this.ctx) return false
    const source = this.ctx.createBufferSource()
    const gain = this.ctx.createGain()
    source.buffer = buffer
    gain.gain.value = 0.95
    source.connect(gain)
    gain.connect(this.masterGain)
    source.start()
    const entry = { source, gain }
    this.active.add(entry)
    source.onended = () => this.active.delete(entry)
    return true
  }

  /* ── 合成兜底 ── */

  playOscillator(midi, durationMs = 1800) {
    const ctx = this.ctx
    if (!ctx) return
    const freq = 440 * 2 ** ((midi - 69) / 12)
    const now = ctx.currentTime
    const dur = durationMs / 1000

    // 基频 + 两个泛音，接近钢琴的衰减音色
    const partials = [
      { mult: 1, amp: 0.5 },
      { mult: 2, amp: 0.18 },
      { mult: 3, amp: 0.07 },
    ]
    for (const p of partials) {
      const osc = ctx.createOscillator()
      const g = ctx.createGain()
      osc.type = 'triangle'
      osc.frequency.value = freq * p.mult
      g.gain.setValueAtTime(0.0001, now)
      g.gain.exponentialRampToValueAtTime(p.amp, now + 0.012)
      g.gain.exponentialRampToValueAtTime(0.0001, now + dur)
      osc.connect(g)
      g.connect(this.masterGain)
      osc.start(now)
      osc.stop(now + dur + 0.05)
      const entry = { source: osc, gain: g }
      this.active.add(entry)
      osc.onended = () => this.active.delete(entry)
    }
  }
}

export const piano = new PianoEngine()
