import React from 'react'
import { Alert, Button } from 'antd'

export default class PageErrorBoundary extends React.Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children
    return <Alert
      type="error"
      showIcon
      message="页面渲染失败"
      description={this.state.error.message || '出现未知错误。'}
      action={<Button size="small" onClick={() => this.setState({ error: null })}>重试</Button>}
    />
  }
}
