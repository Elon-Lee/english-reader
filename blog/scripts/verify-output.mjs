import assert from 'node:assert/strict'
import { readdir, readFile, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../../reader/blog/', import.meta.url))
const config = await readFile(new URL('../src/config.ts', import.meta.url), 'utf8')
const icpRecord = config.match(/export const icpRecord = '([^']*)'/)?.[1] ?? ''
const references = new Set([
  'https://arxiv.org/abs/1706.03762',
  'https://arxiv.org/abs/2005.11401',
  'https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf',
  'https://www.anthropic.com/engineering/building-effective-agents',
])
async function filesIn(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  return (await Promise.all(entries.map(entry => {
    const full = path.join(dir, entry.name)
    return entry.isDirectory() ? filesIn(full) : [full]
  }))).flat()
}

for (const required of ['index.html', 'archives/index.html', 'about/index.html', 'tags/index.html', 'rss.xml', 'atom.xml', 'sitemap-index.xml', 'sitemap-0.xml', 'robots.txt', '404.html']) {
  assert((await stat(path.join(root, required))).isFile(), `Missing ${required}`)
}
const files = await filesIn(root)
const htmlFiles = files.filter(file => file.endsWith('.html'))
const posts = htmlFiles.filter(file => file.includes(`${path.sep}posts${path.sep}`))
assert(posts.length >= 19, 'Expected four English-learning articles plus fifteen existing notes')

for (const file of files.filter(file => /\.(html|xml|xsl|txt|css|js|svg)$/.test(file))) {
  const content = await readFile(file, 'utf8')
  assert(!/learn\.rynenglish\.com|10ye\.cc|\/reader\/(?:app\.js|index\.html)|\/api\/|retypeset-comment|radishzz\.cc|apiflash|googletagmanager|umami|giscus|twikoo|waline/i.test(content), `Unexpected application or third-party integration in ${file}`)
  for (const [url, host] of content.matchAll(/https?:\/\/([^/?#\s"'<>]+)[^\s"'<>]*/g)) {
    const namespaces = ['www.w3.org', 'purl.org', 'www.itunes.com', 'www.sitemaps.org', 'www.google.com', 'validator.w3.org']
    assert(host === 'rynenglish.com' || namespaces.includes(host) || references.has(url) || (icpRecord && host === 'beian.miit.gov.cn'), `Unexpected URL ${url} in ${file}`)
  }
  if (!file.endsWith('.html') && !file.endsWith('.css')) continue
  if (file.endsWith('.html')) {
    assert(content.includes('rel="canonical" href="https://rynenglish.com/'), `Incorrect canonical host in ${file}`)
    for (const [, href] of content.matchAll(/<a\b[^>]*\bhref=["']([^"']+)["']/gi)) {
      if (href.startsWith('#')) continue
      if (references.has(href)) continue
      if (icpRecord && href === 'https://beian.miit.gov.cn/') continue
      assert(!/^(?:https?:)?\/\//.test(href), `Unexpected external navigation ${href} in ${file}`)
      const pathname = decodeURIComponent(href.split(/[?#]/)[0])
      let target = pathname.startsWith('/') ? path.join(root, pathname) : path.resolve(path.dirname(file), pathname)
      if (pathname.endsWith('/')) target = path.join(target, 'index.html')
      assert((await stat(target)).isFile(), `Broken navigation ${href} in ${file}`)
    }
  }
  const resources = file.endsWith('.html')
    ? [...content.matchAll(/<(?:script|img|iframe|audio|video|source)\b[^>]*\bsrc=["']([^"']+)["']|<link\b(?=[^>]*\brel=["'](?:stylesheet|preload|modulepreload|icon)["'])[^>]*\bhref=["']([^"']+)["']/gi)].map(match => match[1] ?? match[2])
    : [...content.matchAll(/url\(["']?([^)'"\s]+)["']?\)/g)].map(match => match[1])
  for (const resource of resources) {
    if (resource.startsWith('data:') || resource.startsWith('#')) continue
    assert(!/^(?:https?:)?\/\//.test(resource), `External resource ${resource} in ${file}`)
    const pathname = decodeURIComponent(resource.split(/[?#]/)[0])
    const local = pathname.startsWith('/') ? path.join(root, pathname) : path.resolve(path.dirname(file), pathname)
    assert(local.startsWith(root), `Resource escapes output: ${resource}`)
    assert((await stat(local)).isFile(), `Missing resource ${resource} in ${file}`)
  }
}

const rss = await readFile(path.join(root, 'rss.xml'), 'utf8')
const article = await readFile(posts[0], 'utf8')
assert(/<button\b(?=[^>]*id="toc-toggle")(?=[^>]*aria-expanded="false")(?=[^>]*aria-controls="toc-accordion-wrapper")/.test(article), 'TOC must expose a native button with its expanded state and controlled panel')
assert(/<div\b(?=[^>]*id="toc-accordion-wrapper")(?=[^>]*\bhidden\b)/.test(article), 'Collapsed TOC panel must be hidden from keyboard navigation')
assert((rss.match(/<item>/g) ?? []).length === Math.min(posts.length, 25), 'RSS must contain the latest 25 published articles, or all when fewer')
assert(rss.includes('https://rynenglish.com/posts/'), 'RSS canonical host is incorrect')
const home = await readFile(path.join(root, 'index.html'), 'utf8')
assert(home.includes('纸间微光') && home.includes('文章归档'), 'Homepage branding/archive missing')
assert(home.includes('把英语') && home.includes('AI 英语工具箱'), 'Homepage must focus on AI-assisted English learning')
assert(!home.includes('慢慢走近') && !home.includes('提示词手记'), 'Retired homepage theme/category still visible')
assert(!files.some(file => file.includes(`${path.sep}categories${path.sep}prompt-notes${path.sep}`)), 'Retired category output still exists')
const archive = await readFile(path.join(root, 'archives/index.html'), 'utf8')
assert((archive.match(/class="archive-entry"/g) ?? []).length === posts.length, 'Archive must include pinned and regular articles')
for (const slug of ['english-tools', 'ai-basics', 'ai-reading', 'practice']) {
  const category = await readFile(path.join(root, 'categories', slug, 'index.html'), 'utf8')
  assert(home.includes(`href="/categories/${slug}/"`), `Homepage missing category ${slug}`)
  const links = [...category.matchAll(/<h3><a href="(\/posts\/[^"]+)"/g)].map(match => match[1])
  assert(links.length >= 3, `Category ${slug} needs at least three articles`)
  if (slug === 'english-tools') assert(links.length >= 4, 'English tools needs four practical articles')
  if (slug === 'ai-reading') {
    for (const moved of ['clear-prompt', 'examples-not-roles', 'check-the-answer']) {
      assert(links.includes(`/posts/${moved}/`), `Moved article missing: ${moved}`)
    }
  }
  for (const href of links) {
    const article = await readFile(path.join(root, href, 'index.html'), 'utf8')
    assert(article.includes(`class="article-category"><a href="/categories/${slug}/"`), `Category mismatch for ${href}`)
  }
}
assert(icpRecord ? home.includes(icpRecord) : !home.includes('beian.miit.gov.cn'), 'ICP display does not match its configuration')
console.log(`Verified ${htmlFiles.length} pages, ${posts.length} articles, feeds, sitemap, local resources and blog isolation.`)
