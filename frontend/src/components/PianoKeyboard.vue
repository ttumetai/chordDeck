<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { midiToNoteName } from '../lib/music.js'

// C3(48) – B4(71)，与钢琴采样范围一致
const START_MIDI = 48
const END_MIDI = 71
const BLACK_PCS = new Set([1, 3, 6, 8, 10])

const props = defineProps({
  // { midi: 级数标签 } 或 null —— 当前和弦点亮表（null/空 = 键盘熄灭）
  highlight: { type: Object, default: null },
})

const containerRef = ref(null)
const width = ref(616) // 默认宽度，挂载后按容器自适应

const WHITE_HEIGHT = 116
const BLACK_HEIGHT = 74

const whites = []
const blacks = []
for (let m = START_MIDI; m <= END_MIDI; m++) {
  if (BLACK_PCS.has(m % 12)) blacks.push(m)
  else whites.push(m)
}

const whiteIndex = computed(() => {
  const w = width.value / whites.length
  return (order) => order * w
})

const geometry = computed(() => {
  const w = width.value / whites.length
  const bw = w * 0.62
  const whiteOrder = new Map()
  whites.forEach((m, i) => whiteOrder.set(m, i))
  return {
    whiteW: w,
    blackW: bw,
    whiteKeys: whites.map((midi) => ({
      midi,
      left: whiteOrder.get(midi) * w,
    })),
    blackKeys: blacks.map((midi) => ({
      midi,
      // 两根白键交界处居中
      left: (whiteOrder.get(midi - 1) + 1) * w - bw / 2,
    })),
  }
})

const keyState = computed(() => {
  const hl = props.highlight || {}
  return (midi) => ({
    active: Object.prototype.hasOwnProperty.call(hl, midi),
    label: hl[midi] || '',
  })
})

let ro = null
onMounted(() => {
  ro = new ResizeObserver(() => {
    const w = containerRef.value?.clientWidth
    if (w && w > 0) width.value = w
  })
  ro.observe(containerRef.value)
})
onUnmounted(() => ro?.disconnect())
</script>

<template>
  <div ref="containerRef" class="piano-shell">
    <div class="piano" :style="{ width: width + 'px', height: WHITE_HEIGHT + 'px' }">
      <!-- 白键 -->
      <div
        v-for="k in geometry.whiteKeys"
        :key="k.midi"
        class="key white"
        :class="{ on: keyState(k.midi).active }"
        :style="{ left: k.left + 'px', width: geometry.whiteW + 'px' }"
      >
        <span class="deg" :class="{ show: keyState(k.midi).active }">
          {{ keyState(k.midi).active ? keyState(k.midi).label : '' }}
        </span>
        <span class="note">{{ midiToNoteName(k.midi) }}</span>
      </div>
      <!-- 黑键 -->
      <div
        v-for="k in geometry.blackKeys"
        :key="k.midi"
        class="key black"
        :class="{ on: keyState(k.midi).active }"
        :style="{
          left: k.left + 'px',
          width: geometry.blackW + 'px',
          height: BLACK_HEIGHT + 'px',
        }"
      >
        <span class="deg black-deg" :class="{ show: keyState(k.midi).active }">
          {{ keyState(k.midi).active ? keyState(k.midi).label : '' }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.piano-shell {
  width: 100%;
  overflow: hidden;
  padding: 10px 0 2px;
}

.piano {
  position: relative;
  margin: 0 auto;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 6px 18px rgba(0, 0, 0, 0.35);
}

.key {
  position: absolute;
  top: 0;
  box-sizing: border-box;
  user-select: none;
}

/* 白键 */
.white {
  height: 100%;
  background: linear-gradient(180deg, #ece9e2, #ddd9d0);
  border-right: 1px solid #b7b2a6;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0 4px;
  transition: background 0.18s ease, filter 0.18s ease;
}
.white:last-child {
  border-right: none;
}
.white .note {
  font-family: var(--font-mono);
  font-size: 9px;
  color: #8a857a;
  letter-spacing: 0.02em;
}
.white .deg {
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 600;
  color: transparent;
}
.white.on {
  background: linear-gradient(180deg, var(--accent), #a08b60);
}
.white.on .note {
  color: rgba(30, 26, 18, 0.75);
}
.white.on .deg.show {
  color: #241f16;
}
.white.on .deg {
  background: rgba(255, 255, 255, 0.14);
  border-radius: 3px;
  padding: 0 3px;
}

/* 黑键 */
.black {
  background: linear-gradient(180deg, #2a2d33, #17181c);
  border-radius: 0 0 3px 3px;
  z-index: 2;
  box-shadow: 0 3px 6px rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 5px;
}
.black .deg {
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 600;
  color: transparent;
}
.black.on {
  background: linear-gradient(180deg, var(--accent), #8d7a52);
}
.black.on .deg.show {
  color: #241f16;
}
</style>
