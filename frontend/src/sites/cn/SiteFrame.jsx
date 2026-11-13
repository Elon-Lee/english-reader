import React from 'react'
import './styles.css'

export default function SiteFrame({ children }) {
  return <div className="cn-site-frame">
    <div className="cn-site-content">{children}</div>
    <footer className="cn-site-footer">
      <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">蜀ICP备2026071122号-1</a>
    </footer>
  </div>
}
