export const bookLevels = [
  { value: 'A1', label: '初级', detail: '零基础或刚入门 · 约 250–700 词 · 能读懂日常简单句和小故事' },
  { value: 'A2', label: '基础', detail: '约 700–1,000 词 · 能连贯阅读简短的日常小说或文章' },
  { value: 'B1', label: '中级', detail: '约 1,000–1,400 词 · 能独立应对大部分通用和生活日常场景' },
  { value: 'B2', label: '中高级', detail: '约 1,800–2,500 词 · 能流畅阅读长篇小说、新闻和专业表达' },
  { value: 'C1', label: '高级', detail: '约 2,500–4,500+ 词 · 接近流利自如的学术或商务交流水平' },
  { value: 'C2', label: '精通级', detail: '母语者水平 · 不封顶 · 原汁原味的纯原版书' },
]

export const bookLevelLabel = value => bookLevels.find(level => level.value === value)?.label || value || ''
