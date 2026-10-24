import React, { useId } from 'react'
import { Radio, theme } from 'antd'

export default function SettingsRadioGroup({ options, value, onChange, id, disabled, label, description }) {
  const fallbackId = useId()
  const { token } = theme.useToken()
  const groupId = id || fallbackId
  const descriptionId = `${groupId}-help`

  return <div className="settings-radio-control" style={{
    '--settings-radio-accent': token.colorPrimary,
    '--settings-radio-surface': token.colorBgContainer,
    '--settings-radio-ink': token.colorText,
    '--settings-radio-muted': token.colorTextSecondary,
    '--settings-radio-disabled': token.colorTextDisabled,
  }}>
    <Radio.Group id={groupId} name={groupId} aria-label={label} aria-describedby={description ? descriptionId : undefined} className="settings-radio-group" value={value} disabled={disabled} options={options} onChange={event => onChange?.(event.target.value)} />
    {description && <div id={descriptionId} className="settings-radio-help" role="status">{description}</div>}
  </div>
}
