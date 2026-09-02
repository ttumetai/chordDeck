// 音乐理论工具：和弦标签解析 → 半音/voicing/级数
// 移植自 chordE (chordFormulas.ts / music.ts)，适配本项目降号记法

export const NOTE_NAMES_FLAT = [
  'C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B',
]

// 兼容升号输入（引擎若输出 C# 也能解析）
const NOTE_ALIASES = {
  C: 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3, E: 4, F: 5,
  'F#': 6, Gb: 6, G: 7, 'G#': 8, Ab: 8, A: 9, 'A#': 10, Bb: 10, B: 11,
}

// 后缀 → 半音集合（0 为根音）
export const CHORD_FORMULAS = [
  { suffix: '', intervals: [0, 4, 7] }, // maj
  { suffix: 'm', intervals: [0, 3, 7] },
  { suffix: 'aug', intervals: [0, 4, 8] },
  { suffix: 'dim', intervals: [0, 3, 6] },
  { suffix: 'sus2', intervals: [0, 2, 7] },
  { suffix: 'sus4', intervals: [0, 5, 7] },
  { suffix: '5', intervals: [0, 7] },
  { suffix: '6', intervals: [0, 4, 7, 9] },
  { suffix: 'm6', intervals: [0, 3, 7, 9] },
  { suffix: '7', intervals: [0, 4, 7, 10] },
  { suffix: 'maj7', intervals: [0, 4, 7, 11] },
  { suffix: 'm7', intervals: [0, 3, 7, 10] },
  { suffix: 'mMaj7', intervals: [0, 3, 7, 11] },
  { suffix: 'dim7', intervals: [0, 3, 6, 9] },
  { suffix: 'm7b5', intervals: [0, 3, 6, 10] },
  { suffix: '7sus4', intervals: [0, 5, 7, 10] },
  { suffix: '7sus2', intervals: [0, 2, 7, 10] },
  { suffix: 'maj7b5', intervals: [0, 4, 6, 11] },
  { suffix: 'add9', intervals: [0, 4, 7, 14] },
  { suffix: 'add11', intervals: [0, 4, 7, 17] },
  { suffix: '6/9', intervals: [0, 4, 7, 9, 14] },
  { suffix: '9', intervals: [0, 4, 7, 10, 14] },
  { suffix: 'maj9', intervals: [0, 4, 7, 11, 14] },
  { suffix: 'm9', intervals: [0, 3, 7, 10, 14] },
  { suffix: '7b9', intervals: [0, 4, 7, 10, 13] },
  { suffix: '7#9', intervals: [0, 4, 7, 10, 15] },
  { suffix: '11', intervals: [0, 4, 7, 10, 14, 17] },
  { suffix: 'm11', intervals: [0, 3, 7, 10, 14, 17] },
  { suffix: '9sus4', intervals: [0, 5, 7, 10, 14] },
  { suffix: '13', intervals: [0, 4, 7, 10, 14, 17, 21] },
  { suffix: '7b5', intervals: [0, 4, 6, 10] },
  { suffix: '7#5', intervals: [0, 4, 8, 10] },
  { suffix: 'maj7#5', intervals: [0, 4, 8, 11] },
]

const FORMULA_MAP = new Map(CHORD_FORMULAS.map((f) => [f.suffix, f.intervals]))

export function mod12(v) {
  return ((v % 12) + 12) % 12
}

export function noteNameToPc(note) {
  const pc = NOTE_ALIASES[note]
  if (pc === undefined) throw new Error(`未知音名: ${note}`)
  return pc
}

export function pcToNoteName(pc) {
  return NOTE_NAMES_FLAT[mod12(pc)]
}

export function midiToPc(midi) {
  return mod12(midi)
}

export function midiToNoteName(midi) {
  const pc = midiToPc(midi)
  const octave = Math.floor(midi / 12) - 1
  return `${pcToNoteName(pc)}${octave}`
}

// 级数标签（移植 chordE intervalToDegreeLabel）
const DEGREE_MAP = {
  0: 'R', 1: 'b9', 2: '9', 3: 'm3', 4: '3', 5: '11', 6: 'b5', 7: '5',
  8: '#5', 9: '6', 10: 'b7', 11: '7', 13: 'b9', 14: '9', 15: '#9',
  17: '11', 18: '#11', 20: 'b13', 21: '13', 22: '#13',
}

export function intervalToDegreeLabel(interval) {
  const normalized = mod12(interval)
  // 9/11/13 需要区分同 pc 的不同级数 → 用原始 interval % 24 保真
  const wide = ((interval % 24) + 24) % 24
  return DEGREE_MAP[wide] ?? DEGREE_MAP[normalized] ?? `${interval}`
}

const ROOT_RE = /^([A-G][#b]?)(.*)$/

/**
 * 解析和弦标签。
 * @returns {{rootPc:number, rootName:string, suffix:string, intervals:number[],
 *            bassPc:number|null, voicingNotes:string[]} | null}
 *          N / 未知 → null
 */
export function parseChordLabel(label) {
  const text = String(label || '').trim()
  if (!text || text === 'N') return null

  // slash chord：D/F#、Eb/G、Am7b5/G
  let bassPc = null
  let main = text
  const slashIdx = text.lastIndexOf('/')
  if (slashIdx > 0) {
    const bass = text.slice(slashIdx + 1).trim()
    if (/^[A-G][#b]?$/.test(bass) && NOTE_ALIASES[bass] !== undefined) {
      bassPc = NOTE_ALIASES[bass]
      main = text.slice(0, slashIdx).trim()
    }
  }

  const m = ROOT_RE.exec(main)
  if (!m) return null
  const rootName = m[1]
  const rootPc = NOTE_ALIASES[rootName]
  if (rootPc === undefined) return null
  let suffix = m[2]

  let intervals = FORMULA_MAP.get(suffix)
  if (!intervals) {
    // 兜底归一化：尽量保留常见性质
    if (suffix.startsWith('maj7')) intervals = FORMULA_MAP.get('maj7')
    else if (suffix.startsWith('m7')) intervals = FORMULA_MAP.get('m7')
    else if (suffix.startsWith('maj')) intervals = FORMULA_MAP.get('')
    else if (suffix.startsWith('m')) intervals = FORMULA_MAP.get('m')
    else if (suffix.startsWith('7')) intervals = FORMULA_MAP.get('7')
    else if (suffix.startsWith('dim')) intervals = FORMULA_MAP.get('dim')
    else if (suffix.startsWith('aug')) intervals = FORMULA_MAP.get('aug')
    else if (suffix.startsWith('sus2')) intervals = FORMULA_MAP.get('sus2')
    else if (suffix.startsWith('sus4')) intervals = FORMULA_MAP.get('sus4')
    else if (suffix.startsWith('5')) intervals = FORMULA_MAP.get('5')
    else intervals = FORMULA_MAP.get('') // 6/9/add9 等 → 大三兜底
    if (!intervals) return null
  }

  // 转位低音音（如有）作为和弦内最低音参与（额外 +12 保证低于其他音不必要——
  // 由 voicing 统一处理；这里仅记录 bassPc 供级数显示）
  return { rootPc, rootName, suffix, intervals, bassPc }
}

/**
 * 紧凑 voicing：根音置于 center（默认 C4=60），各构成音按其 interval 叠加，
 * 超出 [lo, hi]（采样最优点 48..71）时向下折叠八度。
 * @returns {number[]} midi 音符（升序）
 */
/**
 * 根音位置 voicing：根音尽量靠近中央（≈60）且为全和弦最低音，
 * 各构成音向上叠加，超出 [lo, hi]（采样最优点 48..71）时向下折叠八度。
 * @returns {number[]} midi 音符（升序）
 */
export function voicing({ rootPc, intervals, bassPc }, { lo = 48, hi = 71 } = {}) {
  const maxIv = intervals.length ? Math.max(...intervals) : 0
  let root = lo + rootPc
  while (root + maxIv > hi) root -= 12 // 为最高音留出空间
  while (root < 60 && root + 12 + maxIv <= hi) root += 12 // 尽量靠近中央
  const foldDown = (m) => {
    let v = m
    while (v > hi) v -= 12
    return v
  }
  const notes = new Set([root])
  for (const iv of intervals) notes.add(foldDown(root + iv))
  if (bassPc !== null && bassPc !== rootPc) {
    // 转位低音：置于根音下方（同 pc 时并入根音）
    let b = root + mod12(bassPc - rootPc) - 12
    while (b < lo) b += 12
    notes.add(b)
  }
  return Array.from(notes).sort((a, b) => a - b)
}

/** 级数标签（与 intervals 对应，根音标 R） */
export function degreeLabels({ rootPc, intervals, bassPc }) {
  const labels = []
  if (bassPc !== null) labels.push(`/${pcToNoteName(bassPc)}`)
  else labels.push('R')
  for (const iv of intervals) labels.push(intervalToDegreeLabel(iv))
  return labels
}

/** 键盘 24 键（C3..B4）中点亮表：midi → 级数标签（首次出现处标注） */
export function keyboardHighlights({ rootPc, intervals, bassPc }) {
  const mids = voicing({ rootPc, intervals, bassPc })
  const map = new Map()
  const labelByPc = new Map()
  labelByPc.set(mod12(rootPc), 'R')
  if (bassPc !== null && bassPc !== rootPc) labelByPc.set(bassPc, '/')
  for (const iv of intervals) {
    const pc = mod12(rootPc + iv)
    if (!labelByPc.has(pc)) labelByPc.set(pc, intervalToDegreeLabel(iv))
  }
  for (const m of mids) {
    map.set(m, labelByPc.get(midiToPc(m)) || '')
  }
  return map
}
