// 和弦导出工具：CSV / JSON / 和弦谱文本
// 通过系统「另存为」对话框（File System Access API）让用户选择保存目录与文件名；
// 浏览器不支持时回退到默认下载目录（<a download>）。

export function formatTime(t) {
  if (!Number.isFinite(t) || t < 0) t = 0
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function baseName(filename) {
  const base = String(filename || '')
    .replace(/\.[^.]+$/, '')
    .trim()
  return base || 'chords'
}

function extOf(name) {
  const m = String(name).match(/\.([a-z0-9]+)$/i)
  return m ? `.${m[1].toLowerCase()}` : ''
}

function csvCell(v) {
  const s = String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** CSV：与 extract_chords.py 的 --out 输出格式一致（含 BOM，Excel 友好） */
export function buildCsv(chords) {
  const rows = ['timestamp_sec,time,chord']
  for (const c of chords) {
    rows.push(
      [c.timestamp, formatTime(c.timestamp), c.chord].map(csvCell).join(','),
    )
  }
  return '\ufeff' + rows.join('\n') + '\n'
}

/** JSON：完整分析结果 */
export function buildJson(payload) {
  return JSON.stringify(payload, null, 2)
}

/** 和弦谱文本：紧凑进行 + 逐条明细 */
export function buildChordChart(payload) {
  const { filename, duration, source, chords } = payload
  const lines = []
  lines.push(`和弦谱 · ${filename || '未命名'}`)
  lines.push(
    `时长 ${formatTime(duration || 0)} · 识别引擎 ${
      source === 'chordino' ? 'Chordino' : '色度模板匹配'
    }`,
  )
  lines.push('')

  // 紧凑进行
  const progression = chords
    .filter((c) => c.chord !== 'N')
    .map((c) => `${formatTime(c.timestamp)} ${c.chord}`)
  if (progression.length) {
    lines.push('[进行]')
    lines.push(progression.join('  ·  '))
    lines.push('')
  }

  // 明细
  lines.push('[明细]')
  for (const c of chords) {
    lines.push(`${formatTime(c.timestamp)}  ${c.chord}`)
  }
  return lines.join('\n') + '\n'
}

/**
 * 保存文件：优先弹出系统「另存为」对话框（可选择目录与文件名），
 * 用户取消时返回 false；API 不可用或失败时回退默认下载目录并返回 true。
 */
export async function saveFile(name, content, mime) {
  const blob = new Blob([content], { type: mime })

  if (typeof window !== 'undefined' && window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: name,
        types: [
          {
            description: name,
            accept: { [mime]: [extOf(name) || '.bin'] },
          },
        ],
      })
      const writable = await handle.createWritable()
      await writable.write(blob)
      await writable.close()
      return true
    } catch (err) {
      if (err?.name === 'AbortError') return false // 用户在对话框点了取消
      // 其余异常（权限/兼容性问题）→ 走默认下载回退
    }
  }

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return true
}
