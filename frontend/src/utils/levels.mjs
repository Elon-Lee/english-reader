export const bookLevels = [
  { value: 'starter', label: '入门级', detail: 'A1 略低或刚入门 · 约 250–400 词 · 零基础或只认识极其简单的问候语。' },
  { value: 'elementary', label: '初级', detail: 'A1–A2 之间 · 约 400–700 词 · 能读懂包含日常简单句的小故事。' },
  { value: 'pre-intermediate', label: '中下级 / 预备中级', detail: 'A2–B1 之间 · 约 700–1,000 词 · 能够连贯阅读简短的日常小说或文章。' },
  { value: 'intermediate', label: '中级', detail: 'B1 · 约 1,000–1,400 词 · 分水岭，能独立应对大部分通用和生活日常场景。' },
  { value: 'intermediate-plus', label: '中级强化 / 中高级过渡', detail: 'B1+ / B2 预备 · 约 1,400–1,800 词 · B1 升 B2 之间的过渡级。' },
  { value: 'upper-intermediate', label: '中高级', detail: 'B2 · 约 1,800–2,500 词 · 能流畅阅读长篇小说、新闻和专业表达。' },
  { value: 'advanced', label: '高级', detail: 'C1 · 约 2,500–4,500+ 词 · 接近流利自如的学术或商务交流水平。' },
  { value: 'unabridged', label: '未经删节的原版', detail: 'C2 / 母语者水平 · 不封顶 · 原汁原味的纯原版书，未经过词汇简化。' },
]

export const bookLevelLabel = value => bookLevels.find(level => level.value === value)?.label || value || ''
