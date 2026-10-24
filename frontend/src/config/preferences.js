export const DEFAULT_PREFERENCES = {
  theme: 'pine',
  density: 'comfortable',
  readerLayout: 'side',
  eyeComfort: false,
  focusMode: false,
  sentenceAutoPause: false,
  shortcutPrevious: 'a',
  shortcutRepeat: 's',
  shortcutNext: 'd',
  shortcutPlay: 'space',
  playbackRate: 1,
  readerFontSize: 20,
  readerLineHeight: 1.8,
  readerContentWidth: 760,
  readerFlowMode: 'line',
  readerMediaPosition: 0,
  readerToolsPinned: false,
  wordAutoPronounce: false,
  wordHoverPause: false,
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
