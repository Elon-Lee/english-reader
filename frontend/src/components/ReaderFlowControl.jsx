import React from 'react'
import SettingsRadioGroup from './SettingsRadioGroup'

const descriptions = {
  line: '逐句跟随，当前句保持在阅读区约中部。',
  screen: '读到可见区域底部后，再将下一句移到正文顶部。',
}

export default function ReaderFlowControl({ value = 'line', onChange, id, disabled }) {
  const mode = value === 'screen' ? 'screen' : 'line'
  return <SettingsRadioGroup id={id} label="阅读推进方式" value={mode} onChange={onChange} disabled={disabled} description={descriptions[mode]} options={[
    { value: 'line', label: '当前行轮播' },
    { value: 'screen', label: '整屏阅读' },
  ]} />
}
