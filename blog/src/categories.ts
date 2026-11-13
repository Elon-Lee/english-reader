export const categories = [
  { slug: 'english-tools', title: '英语工具', description: '用 AI 整理词汇、练习表达，把方法用在日常学习里。', symbol: '学' },
  { slug: 'ai-basics', title: 'AI 入门', description: '拆开几个概念，让陌生的技术变得可以理解。', symbol: '知' },
  { slug: 'ai-reading', title: 'AI 与阅读', description: '读懂英文，也把问题问清楚，留下自己的理解。', symbol: '读' },
  { slug: 'practice', title: '实践与思考', description: '从小事开始尝试，在使用中保留判断。', symbol: '思' },
] as const

export const categorySlugs = ['english-tools', 'ai-basics', 'ai-reading', 'practice'] as const
export const getCategory = (slug: typeof categorySlugs[number]) => categories.find(category => category.slug === slug)!
