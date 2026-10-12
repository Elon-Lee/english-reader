export const DEFAULT_PREFERENCES = {
  readerMode: 'intensive',
  density: 'comfortable',
  reminder: 'weekdays',
  readerLayout: 'side',
  eyeComfort: false,
  focusMode: false,
  sentenceAutoPause: false,
  shortcutPrevious: 'a',
  shortcutRepeat: 's',
  shortcutNext: 'd',
  shortcutPlay: 'space',
  wordTipSeconds: 2,
  reviewPageSize: 10,
  manualRepeatCount: 3,
  manualPauseSeconds: 2,
  highlightLeadMs: 0,
  heatmapRange: 'year',
  playbackRate: 1,
}

export const KEY_OPTIONS = [
  { value: 'a', label: 'A' },
  { value: 's', label: 'S' },
  { value: 'd', label: 'D' },
  { value: 'space', label: '空格' },
  { value: 'arrowleft', label: '←' },
  { value: 'arrowright', label: '→' },
  { value: 'enter', label: 'Enter' },
]

export function keyboardKey(value) {
  return value === 'space' ? ' ' : value
}
