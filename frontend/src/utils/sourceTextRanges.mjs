const WORD = /[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g
const BLOCKS = new Set(['P', 'DIV', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'BR', 'TR'])

// Index text ranges without inserting spans: original CSS selectors and paragraphs survive.
export function sourceWordRanges(document, section, blocks) {
  const nodes = [], segments = []; let text = ''
  function collect(node) {
    if (node.nodeType === 3) { if (node.data.length) nodes.push({ node, start: text.length, end: text.length + node.data.length }); text += node.data; return }
    if (node.nodeType !== 1 || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(node.tagName)) return
    if (BLOCKS.has(node.tagName)) text += '\n'
    for (const child of node.childNodes) collect(child)
    if (BLOCKS.has(node.tagName)) text += '\n'
  }
  collect(document.body)
  const nodeAt = (offset, end = false) => {
    let left = 0, right = nodes.length
    while (left < right) {
      const middle = (left + right) >>> 1
      if (nodes[middle].end < offset || (!end && nodes[middle].end === offset)) left = middle + 1
      else right = middle
    }
    return nodes[left]
  }
  const tokens = [...text.matchAll(WORD)]
  let cursor = 0
  for (const block of blocks.filter(b => b.section === section)) {
    const expected = [...block.text.matchAll(WORD)].map(m => m[0])
    if (!expected.length) continue
    let start = -1
    for (let i = cursor; i + expected.length <= tokens.length; i++) {
      if (expected.every((word, j) => word === tokens[i + j][0])) { start = i; break }
    }
    if (start < 0) continue
    for (let i = 0; i < expected.length; i++) {
      const token = tokens[start + i], begin = token.index, end = begin + token[0].length
      const first = nodeAt(begin), last = nodeAt(end, true)
      if (!first || !last || !block.words?.[i]) continue
      const range = document.createRange(); range.setStart(first.node, begin - first.start); range.setEnd(last.node, end - last.start)
      segments.push({ range, offset: begin, text: token[0], ...block.words[i] })
    }
    cursor = start + expected.length
  }
  return segments
}
