import type { Language } from '@/i18n/config'
interface Translation {
  title: string; subtitle: string; description: string
  posts: string; tags: string; about: string; toc: string
}
export const ui: Record<Language, Translation> = {
  zh: {
    title: '纸间微光', subtitle: '一页一光，静读慢行。',
    description: '一个记录阅读、写作与日常思考的个人博客。',
    posts: '文章', tags: '标签归档', about: '关于', toc: '目录',
  },
}
