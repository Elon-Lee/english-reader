import { unzipSync, strFromU8 } from 'fflate'
import createDOMPurify from 'dompurify'
import * as css from 'css-tree'

const TYPES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml', woff: 'font/woff', woff2: 'font/woff2', ttf: 'font/ttf', otf: 'font/otf' }

export function archivePath(base, href) {
  if (!href || /^[a-z][a-z\d+.-]*:|^[/\\]/i.test(href)) return null
  let path
  try { path = decodeURIComponent(href.split(/[?#]/)[0]) } catch { return null }
  const output = base.split('/').slice(0, -1)
  for (const part of path.split('/')) {
    if (part === '..') { if (!output.length) return null; output.pop() }
    else if (part && part !== '.') output.push(part)
  }
  return output.join('/')
}

export function openEpubArchive(bytes) {
  let size = 0, count = 0
  const files = unzipSync(new Uint8Array(bytes), { filter(file) {
    size += file.originalSize; count++
    if (count > 10000 || file.originalSize > 20 * 1024 * 1024 || size > 200 * 1024 * 1024 || file.name.includes('\\') || archivePath('', file.name) !== file.name.replace(/\/$/, '')) throw new Error('EPUB 内容路径或解压大小无效')
    return !file.name.endsWith('/')
  } })
  if (files['META-INF/encryption.xml']) throw new Error('此 EPUB 含加密资源，暂不支持原版阅读')
  const urls = new Map()
  const asset = (base, href) => {
    const name = archivePath(base, href), type = TYPES[name?.split('.').at(-1).toLowerCase()]
    if (!name || !files[name] || !type) return ''
    if (!urls.has(name)) urls.set(name, URL.createObjectURL(new Blob([files[name]], { type })))
    return urls.get(name)
  }
  const stylesheet = (name, visited = new Set()) => {
    if (!files[name] || visited.has(name) || visited.size > 32) return ''
    const next = new Set(visited).add(name)
    return cleanCss(strFromU8(files[name]), name, next)
  }
  const cleanCss = (value, base, visited = new Set(), context = 'stylesheet') => {
    let tree
    try { tree = css.parse(value, { context, parseCustomProperty: true }) } catch { return '' }
    css.walk(tree, { visit: 'Atrule', enter(node, item, list) {
      if (node.name.toLowerCase() === 'import') {
        const first = node.prelude?.children?.first
        const target = first && ['String', 'Url'].includes(first.type) ? archivePath(base, first.value) : null
        const rest = node.prelude ? css.generate(node.prelude).replace(/^(?:url\([^)]*\)|"[^"]*"|'[^']*')\s*/, '') : ''
        const imported = target ? stylesheet(target, visited) : ''
        // Imported CSS stays in its original cascade position; media conditions survive.
        const replacement = imported ? css.parse(rest ? `@media ${rest}{${imported}}` : imported).children : null
        if (replacement) list.insertList(replacement, item)
        list.remove(item)
      } else if (['charset', 'namespace'].includes(node.name.toLowerCase())) list.remove(item)
    } })
    css.walk(tree, { visit: 'Url', enter(node) { if (![...urls.values()].includes(node.value)) node.value = asset(base, node.value) || 'data:,' } })
    return css.generate(tree)
  }
  return {
    navigation(spine, blocks = []) {
      const parse = name => new DOMParser().parseFromString(strFromU8(files[name]), 'application/xml')
      const container = files['META-INF/container.xml'] && parse('META-INF/container.xml')
      const packagePath = container?.getElementsByTagName('rootfile')[0]?.getAttribute('full-path')
      const opf = packagePath && files[packagePath] && parse(packagePath)
      const items = [...(opf?.getElementsByTagName('item') || [])]
      const nav = items.find(item => item.getAttribute('properties')?.split(/\s+/).includes('nav'))
      const ncx = items.find(item => item.getAttribute('media-type') === 'application/x-dtbncx+xml')
      const name = (nav || ncx) && archivePath(packagePath, (nav || ncx).getAttribute('href'))
      let entries = []
      if (name && files[name]) {
        const document = parse(name)
        const toc = nav ? [...document.getElementsByTagName('nav')].find(node => (node.getAttribute('epub:type') || node.getAttribute('role') || '').split(/\s+/).some(type => ['toc', 'doc-toc'].includes(type))) : document
        entries = [...(toc?.getElementsByTagName(nav ? 'a' : 'navPoint') || [])].map(node => {
          const href = nav ? node.getAttribute('href') : node.getElementsByTagName('content')[0]?.getAttribute('src')
          const chapter = spine.findIndex(item => item.href === archivePath(name, href))
          let elementId = ''
          try { elementId = decodeURIComponent(href?.split('#')[1] || '') } catch { return null }
          const label = nav ? node.textContent : node.getElementsByTagName('navLabel')[0]?.textContent
          let depth = 0, parent = node.parentElement
          while (parent && parent !== toc) { if (parent.localName === (nav ? 'ol' : 'navPoint')) depth++; parent = parent.parentElement }
          return chapter >= 0 && label?.trim() ? { chapter, elementId, title: label.trim(), depth: Math.max(0, depth - (nav ? 1 : 0)) } : null
        }).filter(Boolean)
      }
      const headings = blocks.filter(block => block.type === 'heading').map(block => ({
        chapter: spine.findIndex(item => item.section === block.section), title: block.text,
        sentenceId: block.words?.[0]?.sentenceId, depth: 0,
      })).filter(entry => entry.chapter >= 0 && entry.sentenceId)
      const chapters = headings.filter(entry => /^(?:chapter|part|book)\s+\S|^第.+[章节卷部]/i.test(entry.title.trim()))
      // Some EPUBs declare only a cover/Start NCX. Actual chapter headings remain navigable.
      if (chapters.length > entries.length || (chapters.length && !entries.some(entry => entry.elementId))) return chapters
      if (entries.length) return entries
      if (headings.length) return headings
      return spine.map((item, chapter) => ({ chapter, title: `第 ${chapter + 1} ${item.layout === 'fixed' ? '页' : '节'}`, depth: 0 }))
    },
    chapter(href) {
      if (!files[href]) throw new Error('EPUB 原章节不存在')
      const raw = strFromU8(files[href])
      // Read numeric layout metadata before sanitization removes author meta tags.
      const viewportTag = (raw.match(/<meta\b[^>]*>/gi) || []).find(tag => /\bname\s*=\s*['"]viewport['"]/i.test(tag)) || ''
      const viewport = viewportTag.match(/\bcontent\s*=\s*(['"])(.*?)\1/i)?.[2] || ''
      const purifier = createDOMPurify(window)
      const clean = purifier.sanitize(raw, { WHOLE_DOCUMENT: true, ADD_TAGS: ['link', 'style'],
        FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'base', 'audio', 'video', 'source', 'foreignObject', 'animate', 'set'],
        FORBID_ATTR: ['srcset', 'srcdoc', 'autofocus', 'formaction', 'ping', 'target'], ADD_ATTR: ['epub:type'] })
      const document = new DOMParser().parseFromString(clean, 'text/html')
      for (const node of document.querySelectorAll('meta,base')) node.remove()
      for (const node of document.querySelectorAll('link')) {
        if (node.rel === 'stylesheet') {
          const name = archivePath(href, node.getAttribute('href'))
          const style = document.createElement('style'); style.textContent = name ? stylesheet(name) : ''; node.replaceWith(style)
        } else node.remove()
      }
      for (const node of document.querySelectorAll('style')) node.textContent = cleanCss(node.textContent, href)
      for (const node of document.querySelectorAll('[style]')) node.setAttribute('style', cleanCss(node.getAttribute('style'), href, new Set(), 'declarationList'))
      for (const node of document.querySelectorAll('[src],[href],[xlink\\:href]')) {
        for (const key of ['src', 'href', 'xlink:href']) {
          const value = node.getAttribute(key)
          if (value == null) continue
          if (node.localName === 'a' && key === 'href') {
            // Parent handles internal chapter/footnote navigation; no arbitrary navigation.
            node.dataset.epubLink = value; node.removeAttribute(key)
          } else node.setAttribute(key, value.startsWith('#') ? value : asset(href, value) || 'data:,')
        }
      }
      const policy = document.createElement('meta'); policy.httpEquiv = 'Content-Security-Policy'
      policy.content = "default-src 'none'; img-src blob: data:; font-src blob: data:; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
      document.head.prepend(policy)
      return { html: '<!doctype html>\n' + document.documentElement.outerHTML, viewport }
    },
    close() { for (const url of urls.values()) URL.revokeObjectURL(url); urls.clear() },
  }
}

export { sourceWordRanges } from './sourceTextRanges.mjs'
