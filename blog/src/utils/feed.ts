import type { APIContext } from 'astro'
import type { Language } from '@/i18n/config'
import { getCollection } from 'astro:content'
import { Feed } from 'feed'
import MarkdownIt from 'markdown-it'
import sanitizeHtml from 'sanitize-html'
import { themeConfig } from '@/config'
import { getPostDescription } from '@/utils/description'

const markdownParser = new MarkdownIt()
const { title, description, url, author } = themeConfig.site

export async function generateFeed({ lang }: { lang?: Language } = {}) {
  const posts = (await getCollection('posts', ({ data }) =>
    !data.draft && (!data.lang || data.lang === (lang ?? 'zh')),
  )).sort((a, b) => b.data.published.valueOf() - a.data.published.valueOf()).slice(0, 25)
  const feed = new Feed({
    title, description, id: url, link: url, language: 'zh-CN',
    copyright: `© ${new Date().getFullYear()} ${author}`,
    updated: posts[0]?.data.updated ?? posts[0]?.data.published ?? new Date('2026-11-11'),
    generator: 'Astro · Retypeset',
    feedLinks: { rss: `${url}/rss.xml`, atom: `${url}/atom.xml` },
    author: { name: author, link: url },
  })
  for (const post of posts) {
    const link = new URL(`posts/${post.data.abbrlink || post.id}/`, url).href
    feed.addItem({
      title: post.data.title, id: link, link,
      description: getPostDescription(post, 'feed'),
      content: sanitizeHtml(markdownParser.render(post.body ?? '')),
      author: [{ name: author, link: url }],
      published: post.data.published,
      date: post.data.updated ?? post.data.published,
    })
  }
  return feed
}
export async function generateRSS(_context: APIContext) {
  const feed = await generateFeed()
  const xml = feed.rss2().replace('?>', '?>\n<?xml-stylesheet href="/feeds/rss-style.xsl" type="text/xsl"?>')
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } })
}
export async function generateAtom(_context: APIContext) {
  const feed = await generateFeed()
  const xml = feed.atom1().replace('?>', '?>\n<?xml-stylesheet href="/feeds/atom-style.xsl" type="text/xsl"?>')
  return new Response(xml, { headers: { 'Content-Type': 'application/atom+xml; charset=utf-8' } })
}
