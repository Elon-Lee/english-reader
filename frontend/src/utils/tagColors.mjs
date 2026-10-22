const palette = ['blue', 'cyan', 'green', 'orange', 'magenta', 'purple', 'volcano', 'geekblue', 'gold', 'lime']

export function tagColor(value = '') {
  let hash = 0
  for (const char of String(value)) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return palette[hash % palette.length]
}
