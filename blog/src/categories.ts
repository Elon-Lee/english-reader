export const categories = [
  { slug: 'ai-basics', title: 'AI 入门', description: '拆开几个概念，让陌生的技术变得可以理解。', symbol: '知' },
  { slug: 'prompt-notes', title: '提示词手记', description: '把问题问具体，也给答案留一把尺子。', symbol: '问' },
  { slug: 'ai-reading', title: 'AI 与阅读', description: '借一束新的光，照见文字里的细节。', symbol: '读' },
  { slug: 'practice', title: '实践与思考', description: '从小事开始尝试，在使用中保留判断。', symbol: '思' },
] as const

export const categorySlugs = ['ai-basics', 'prompt-notes', 'ai-reading', 'practice'] as const
export const getCategory = (slug: typeof categorySlugs[number]) => categories.find(category => category.slug === slug)!
