<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import PianoKeyboard from './PianoKeyboard.vue'
import { keyboardHighlights, parseChordLabel, voicing } from '../lib/music.js'
import { piano } from '../lib/piano.js'
import { bus } from '../lib/events.js'

const props = defineProps({
  audioUrl: { type: String, required: true },
  chords: { type: Array, required: true }, // [{ timestamp, chord }]
  filename: { type: String, default: '' },
  duration: { type: Number, default: null }, // 后端预估时长（备用）
})

const audioRef = ref(null)
const innerRef = ref(null)

const playing = ref(false)
const current = ref(0)
const dur = ref(0)
const ready = ref(false)
const dragging = ref(false)
const trackW = ref(0)
const hover = ref(null) // { x: px, t: sec }

let raf = null
let ro = null
let lastIdxBeforeDrag = -1
let lastAutoIdx = -1

const audio = () => audioRef.value

/* ── 钢琴 / 音量 / 偏移（持久化） ── */

const LS = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(key)
      return v === null ? fallback : v
    } catch {
      return fallback
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value)
    } catch {
      /* ignore */
    }
  },
}

const pianoOn = ref(LS.get('chord:pianoOn', '0') === '1')
const volOriginal = ref(Number(LS.get('chord:volOriginal', '80')))
const volPiano = ref(Number(LS.get('chord:volPiano', '55')))
const offsetTicks = ref(Number(LS.get(`chord:offset:${props.audioUrl}`, '0')) || 0)

const offsetSec = computed(() => offsetTicks.value * 0.1)
const offsetText = computed(() => {
  const s = (Math.abs(offsetTicks.value) / 10).toFixed(1)
  return `${offsetTicks.value >= 0 ? '+' : '-'}${s}s`
})

function offsetStep(dir) {
  offsetTicks.value = Math.max(-50, Math.min(50, offsetTicks.value + dir))
}

watch(pianoOn, (v) => {
  piano.enabled = v
  if (v) {
    piano.unlock()
    piano.setVolume(volPiano.value / 100)
  } else {
    piano.stop()
  }
  LS.set('chord:pianoOn', v ? '1' : '0')
})
watch(volOriginal, (v) => {
  if (audio()) audio().volume = v / 100
  LS.set('chord:volOriginal', String(v))
})
watch(volPiano, (v) => {
  piano.setVolume(v / 100)
  LS.set('chord:volPiano', String(v))
})
watch(offsetTicks, (v) => LS.set(`chord:offset:${props.audioUrl}`, String(v)))

function togglePiano() {
  pianoOn.value = !pianoOn.value
}

/* ── 和弦查询（基于 effective 时间） ── */

const effective = computed(() => current.value + offsetSec.value)

// 找到 effective 时刻生效的和弦标记（最后一个 start <= t）
const activeIdx = computed(() => {
  const d = dur.value
  if (!d || !props.chords.length) return -1
  const t = effective.value
  if (t < props.chords[0].timestamp) return -1
  let idx = -1
  for (let i = 0; i < props.chords.length; i++) {
    if (props.chords[i].timestamp <= t) idx = i
    else break
  }
  return idx
})

const currentChord = computed(() =>
  activeIdx.value >= 0 ? props.chords[activeIdx.value] : null,
)

const chordParsed = computed(() => {
  const c = currentChord.value
  if (!c || c.chord === 'N') return null
  return parseChordLabel(c.chord)
})

const keyHighlight = computed(() => {
  const p = chordParsed.value
  return p ? Object.fromEntries(keyboardHighlights(p)) : null
})

const canAudition = computed(() => Boolean(chordParsed.value) && pianoOn.value)

function playChordNow() {
  const p = chordParsed.value
  if (!p) return
  piano.playChord(voicing(p))
}

function audition() {
  if (!canAudition.value) return
  playChordNow()
}

/* ── 时间轴数据 ── */

// 标记点：按时间百分比定位；标签过密时只保留刻度（title 提示和弦）
const markers = computed(() => {
  const d = dur.value
  if (!d || !props.chords.length) return []
  const innerW = trackW.value || 800
  const labelMin = 48 // 两个标签之间的最小像素间距
  let lastLabelX = -Infinity
  return props.chords.map((c, i) => {
    const px = (c.timestamp / d) * innerW
    const next = props.chords[i + 1]
    const gapPx = next ? ((next.timestamp - c.timestamp) / d) * innerW : Infinity
    const noise = c.chord === 'N'
    const showLabel = !noise && px - lastLabelX >= labelMin
    if (showLabel) lastLabelX = px
    return {
      idx: i,
      t: c.timestamp,
      chord: c.chord,
      left: (c.timestamp / d) * 100,
      noise,
      showLabel,
    }
  })
})

// 当前和弦覆盖的片段（按 effective 判定，用于浅色高亮）
const activeBand = computed(() => {
  const idx = activeIdx.value
  const d = dur.value
  if (idx < 0 || !d) return null
  const start = props.chords[idx].timestamp
  const end =
    idx + 1 < props.chords.length ? props.chords[idx + 1].timestamp : d
  return {
    l: (start / d) * 100,
    w: Math.max(((end - start) / d) * 100, 0.4),
  }
})

const playLeft = computed(() =>
  dur.value ? Math.min((current.value / dur.value) * 100, 100) : 0,
)

const isActive = (m) => m.idx === activeIdx.value

/* ── 播放控制 ── */

function toggle() {
  const el = audio()
  if (!ready.value) return
  if (el.paused) {
    if (el.ended || dur.value - el.currentTime < 0.05) el.currentTime = 0
    el.play()
    playing.value = true
    if (pianoOn.value) piano.unlock()
    raf = requestAnimationFrame(loop)
  } else {
    el.pause()
    playing.value = false
    cancelAnimationFrame(raf)
  }
}

function loop() {
  const el = audio()
  if (!el.paused) {
    current.value = el.currentTime
    raf = requestAnimationFrame(loop)
  }
}

// 自动试听：播放中跨入新和弦时触发
watch(activeIdx, (idx, prev) => {
  if (idx === prev) return
  if (playing.value && pianoOn.value && !dragging.value) playChordNow()
})

function fmt(t) {
  if (!Number.isFinite(t) || t < 0) t = 0
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/* ── 时间轴交互 ── */

function posFromEvent(e) {
  const rect = innerRef.value.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
  return ratio * dur.value
}

function seekTo(t) {
  if (!ready.value) return
  const el = audio()
  const clamped = Math.min(Math.max(0, t), dur.value)
  el.currentTime = clamped
  current.value = clamped
}

function onPointerDown(e) {
  if (!ready.value) return
  dragging.value = true
  lastIdxBeforeDrag = activeIdx.value
  innerRef.value.setPointerCapture(e.pointerId)
  seekTo(posFromEvent(e))
}

function onPointerMove(e) {
  if (!dur.value) return
  const rect = innerRef.value.getBoundingClientRect()
  hover.value = { x: e.clientX - rect.left, t: posFromEvent(e) }
  if (dragging.value) seekTo(hover.value.t)
}

function onPointerUp() {
  if (dragging.value) {
    // 松手后若和弦已变化，补一次试听便于核对
    if (pianoOn.value && activeIdx.value !== lastIdxBeforeDrag) playChordNow()
  }
  dragging.value = false
}

function onPointerLeave() {
  hover.value = null
}

/* ── 生命周期 ── */

function pausePlayback() {
  const el = audio()
  if (el && !el.paused) {
    el.pause()
    playing.value = false
    cancelAnimationFrame(raf)
  }
}

function onKeydown(e) {
  if (document.body.classList.contains('modal-open')) return // 模态面板打开时不响应
  if (e.code === 'Space' && !e.target.closest('button, input, textarea')) {
    e.preventDefault()
    toggle()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  bus.on('player:pause', pausePlayback)
  ro = new ResizeObserver(() => {
    trackW.value = innerRef.value?.clientWidth || 0
  })
  ro.observe(innerRef.value)
  // 初始同步
  piano.enabled = pianoOn.value
  piano.setVolume(volPiano.value / 100)
  if (audio()) audio().volume = volOriginal.value / 100
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  bus.off('player:pause', pausePlayback)
  ro?.disconnect()
  cancelAnimationFrame(raf)
  piano.stop()
})
</script>

<template>
  <div class="player">
    <audio
      ref="audioRef"
      :src="audioUrl"
      preload="metadata"
      @loadedmetadata="dur = audio().duration || props.duration || 0; ready = true"
      @timeupdate="current = audio().currentTime"
      @ended="playing = false; current = dur"
    ></audio>

    <!-- 顶部：当前和弦 + 键盘 + 文件信息 -->
    <div class="player-top">
      <div class="chord-now">
        <span class="caption">当前和弦</span>
        <div class="chord-line">
          <span class="chord-name" :class="{ noise: !currentChord || currentChord.chord === 'N' }">
            {{ currentChord ? currentChord.chord : '—' }}
          </span>
          <button
            class="audition"
            :disabled="!canAudition"
            :title="pianoOn ? '试听当前和弦的钢琴声' : '请先开启钢琴声音'"
            @click="audition"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M7 4.5v11l9-5.5z" fill="currentColor" />
            </svg>
            试听
          </button>
        </div>
      </div>
      <div class="player-meta">
        <span class="file" :title="filename">{{ filename }}</span>
        <span class="time mono">{{ fmt(current) }} / {{ fmt(dur) }}</span>
      </div>
    </div>

    <!-- 钢琴键盘：点亮当前和弦构成音 -->
    <PianoKeyboard :highlight="keyHighlight" />

    <!-- 时间轴：进度条 + 和弦标点 -->
    <div
      class="timeline"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerLeave"
    >
      <div ref="innerRef" class="timeline-inner">
        <div class="rail"></div>
        <div class="fill" :style="{ width: playLeft + '%' }"></div>

        <!-- 当前和弦覆盖片段 -->
        <div
          v-if="activeBand"
          class="active-band"
          :style="{ left: activeBand.l + '%', width: activeBand.w + '%' }"
        ></div>

        <!-- 和弦标点 -->
        <template v-for="m in markers" :key="m.idx">
          <div
            class="marker"
            :class="{ active: isActive(m), noise: m.noise, labeled: m.showLabel }"
            :style="{ left: m.left + '%' }"
            :title="`${m.chord} · ${fmt(m.t)}`"
          >
            <span v-if="m.showLabel" class="mlabel">{{ m.chord }}</span>
            <span class="mtick"></span>
          </div>
        </template>

        <!-- 悬停刻度 -->
        <div v-if="hover && !dragging" class="hover-line" :style="{ left: hover.x + 'px' }">
          <span class="hover-time mono">{{ fmt(hover.t) }}</span>
        </div>

        <!-- 播放头 -->
        <div class="playhead" :style="{ left: playLeft + '%' }">
          <span class="ph-dot"></span>
        </div>
      </div>
    </div>

    <!-- 控制栏 -->
    <div class="transport">
      <button
        class="play"
        :class="{ playing }"
        :disabled="!ready"
        :aria-label="playing ? '暂停' : '播放'"
        @click="toggle"
      >
        <svg v-if="!playing" viewBox="0 0 20 20" aria-hidden="true">
          <path d="M7 4.5v11l9-5.5z" fill="currentColor" />
        </svg>
        <svg v-else viewBox="0 0 20 20" aria-hidden="true">
          <path d="M6 4.5h2.6v11H6zM11.4 4.5H14v11h-2.6z" fill="currentColor" />
        </svg>
      </button>
      <span class="time-current mono">{{ fmt(current) }}</span>
      <span class="time-total mono">/ {{ fmt(dur) }}</span>
      <span class="grow"></span>
      <span class="caption hint">空格键 播放 / 暂停</span>
    </div>

    <!-- 核对设置行 -->
    <div class="settings">
      <button
        class="switch"
        :class="{ on: pianoOn }"
        :aria-pressed="pianoOn"
        role="switch"
        @click="togglePiano"
      >
        <span class="switch-knob"></span>
      </button>
      <span class="caption">钢琴声音</span>
      <span class="s-sep"></span>

      <label class="vol">
        <span class="caption">原曲</span>
        <input
          v-model.number="volOriginal"
          type="range"
          min="0"
          max="100"
          step="1"
        />
        <span class="vol-val mono">{{ volOriginal }}</span>
      </label>

      <label class="vol">
        <span class="caption">钢琴</span>
        <input
          v-model.number="volPiano"
          type="range"
          min="0"
          max="100"
          step="1"
        />
        <span class="vol-val mono">{{ volPiano }}</span>
      </label>

      <span class="s-sep"></span>

      <div class="offset" :title="'和弦时间偏移：正值 = 和弦判定延后（标记比听感早时调 +）'">
        <span class="caption">和弦偏移</span>
        <button class="o-btn" :disabled="offsetTicks <= -50" @click="offsetStep(-1)">−</button>
        <span class="offset-val mono">{{ offsetText }}</span>
        <button class="o-btn" :disabled="offsetTicks >= 50" @click="offsetStep(1)">+</button>
        <button v-if="offsetTicks" class="o-reset" @click="offsetTicks = 0">归零</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player {
  padding: 34px 34px 22px;
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
}

/* ── 顶部 ── */
.player-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
}

.chord-now {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chord-line {
  display: flex;
  align-items: center;
  gap: 14px;
}

.chord-name {
  font-family: var(--font-serif);
  font-size: 42px;
  line-height: 1.05;
  letter-spacing: 0.05em;
  color: var(--text);
  transition: color 0.25s ease;
}
.chord-name.noise {
  color: var(--text-faint);
  font-size: 30px;
}

.audition {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 11.5px;
  letter-spacing: 0.1em;
  color: var(--text-dim);
  transition: color 0.22s ease, border-color 0.22s ease, background 0.22s ease;
}
.audition svg {
  width: 11px;
  height: 11px;
}
.audition:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.audition:disabled {
  opacity: 0.4;
  cursor: default;
}

.player-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  min-width: 0;
}
.file {
  font-size: 12px;
  color: var(--text-dim);
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.time {
  font-size: 12px;
  color: var(--text-faint);
}

/* ── 时间轴 ── */
.timeline {
  padding: 4px 30px 2px;
  cursor: pointer;
  touch-action: none;
  user-select: none;
}

.timeline-inner {
  position: relative;
  height: 92px;
}

.rail {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 2px;
  border-radius: 1px;
  background: var(--border);
  transform: translateY(-50%);
}

.fill {
  position: absolute;
  top: 50%;
  left: 0;
  height: 2px;
  border-radius: 1px;
  transform: translateY(-50%);
  background: linear-gradient(90deg, var(--accent-line), var(--accent));
  pointer-events: none;
}

.active-band {
  position: absolute;
  top: 50%;
  height: 18px;
  border-radius: 9px;
  transform: translateY(-50%);
  background: var(--accent-soft);
  border: 1px solid var(--accent-line);
  pointer-events: none;
  z-index: 0;
}

/* 和弦标点 */
.marker {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  z-index: 1;
}

.mtick {
  width: 1px;
  height: 12px;
  background: var(--text-faint);
  transition: background 0.2s ease, height 0.2s ease;
}

.mlabel {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  white-space: nowrap;
  transition: color 0.2s ease;
}

.marker.noise .mtick {
  height: 7px;
  background: var(--border);
}

.marker.active .mtick {
  height: 16px;
  background: var(--accent);
}
.marker.active .mlabel {
  color: var(--accent);
}
.marker:hover .mtick {
  background: var(--accent);
}
.marker:hover .mlabel {
  color: var(--text);
}

/* 悬停刻度 */
.hover-line {
  position: absolute;
  top: 2px;
  bottom: 2px;
  width: 1px;
  background: rgba(255, 255, 255, 0.16);
  pointer-events: none;
  z-index: 3;
}
.hover-time {
  position: absolute;
  top: 0;
  left: 9px;
  font-size: 10px;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
  letter-spacing: 0.06em;
  white-space: nowrap;
}

/* 播放头 */
.playhead {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
}
.ph-dot {
  display: block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--surface), 0 0 0 4px var(--accent-line);
}

/* ── 控制栏 ── */
.transport {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
}

.play {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid var(--border);
  display: grid;
  place-items: center;
  color: var(--text);
  transition: border-color 0.25s ease, color 0.25s ease,
    background 0.25s ease;
}
.play svg {
  width: 17px;
  height: 17px;
}
.play:hover:not(:disabled) {
  border-color: var(--accent-line);
  color: var(--accent);
  background: var(--accent-soft);
}
.play.playing {
  color: var(--accent);
  border-color: var(--accent-line);
}
.play:disabled {
  opacity: 0.45;
  cursor: default;
}

.time-current {
  font-size: 13px;
  color: var(--text-dim);
}
.time-total {
  font-size: 13px;
  color: var(--text-faint);
}
.grow {
  flex: 1;
}
.hint {
  letter-spacing: 0.16em;
}

/* ── 核对设置行 ── */
.settings {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-soft);
  flex-wrap: wrap;
}

.s-sep {
  width: 1px;
  height: 18px;
  background: var(--border-soft);
  margin: 0 2px;
}

/* 开关 */
.switch {
  position: relative;
  width: 34px;
  height: 19px;
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
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: var(--text-faint);
  transition: left 0.25s ease, background 0.25s ease;
}
.switch.on {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.switch.on .switch-knob {
  left: 17px;
  background: var(--accent);
}

/* 音量 */
.vol {
  display: flex;
  align-items: center;
  gap: 8px;
}
.vol input[type='range'] {
  -webkit-appearance: none;
  appearance: none;
  width: 96px;
  height: 2px;
  border-radius: 1px;
  background: var(--border);
  outline: none;
  cursor: pointer;
}
.vol input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
  transition: transform 0.15s ease;
}
.vol input[type='range']::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}
.vol input[type='range']::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
}
.vol-val {
  font-size: 10.5px;
  color: var(--text-faint);
  width: 22px;
  text-align: right;
}

/* 偏移 */
.offset {
  display: flex;
  align-items: center;
  gap: 6px;
}
.o-btn {
  width: 22px;
  height: 22px;
  border: 1px solid var(--border);
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  line-height: 1;
  color: var(--text-dim);
  transition: color 0.2s ease, border-color 0.2s ease;
}
.o-btn:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent-line);
}
.o-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
.offset-val {
  font-size: 11.5px;
  color: var(--text-dim);
  min-width: 44px;
  text-align: center;
  letter-spacing: 0.04em;
}
.o-reset {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--text-faint);
  padding: 3px 8px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  transition: color 0.2s ease, border-color 0.2s ease;
}
.o-reset:hover {
  color: var(--accent);
  border-color: var(--accent-line);
}
</style>
