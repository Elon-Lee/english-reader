import type { ThemeConfig } from '@/types'

export const themeConfig: ThemeConfig = {
  site: {
    title: '纸间微光',
    subtitle: '借 AI 微光，让英语学习有章可循。',
    description: '纸间微光，记录 AI 英语工具与学习方法的个人博客。分享词汇整理、口语练习、英文写作和听力复盘的操作步骤与提示模板。',
    i18nTitle: false,
    author: '纸间微光',
    url: 'https://rynenglish.com',
    base: '/',
    favicon: '/icons/favicon.svg',
  },
  color: {
    mode: 'light',
    light: {
      primary: '#3d352d',
      secondary: '#756b5e',
      background: '#f8f5ed',
      highlight: '#eacb9b88',
    },
    dark: {
      primary: '#e9dfcf',
      secondary: '#c1b3a0',
      background: '#28251f',
      highlight: '#b8864c55',
    },
  },
  global: {
    locale: 'zh',
    moreLocales: [],
    fontStyle: 'serif',
    dateFormat: 'YYYY-MM-DD',
    toc: true,
    katex: false,
    reduceMotion: true,
  },
  comment: { enabled: false },
  footer: { links: [{ name: 'RSS', url: '/rss.xml' }], startYear: 2026 },
}

// 取得真实备案号后填写；空值时不渲染备案链接。
export const icpRecord = ''
export const base = themeConfig.site.base === '/' ? '' : themeConfig.site.base.replace(/\/$/, '')
export const defaultLocale = themeConfig.global.locale
export const moreLocales = themeConfig.global.moreLocales
export const allLocales = [defaultLocale, ...moreLocales]
