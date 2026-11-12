import sitemap from '@astrojs/sitemap'
import { unified } from '@astrojs/markdown-remark'
import { defineConfig } from 'astro/config'
import rehypeSlug from 'rehype-slug'
import UnoCSS from 'unocss/astro'
import { defaultLocale, themeConfig } from './src/config'
import { rehypeCodeCopyButton } from './src/plugins/rehype-code-copy-button.mjs'
import { rehypeExternalLinks } from './src/plugins/rehype-external-links.mjs'
import { rehypeHeadingAnchor } from './src/plugins/rehype-heading-anchor.mjs'
import { remarkReadingTime } from './src/plugins/remark-reading-time.mjs'

export default defineConfig({
  site: themeConfig.site.url,
  output: 'static',
  outDir: '../reader/blog',
  trailingSlash: 'always',
  i18n: { locales: ['zh'], defaultLocale },
  integrations: [UnoCSS({ injectReset: true }), sitemap({ filter: page => !page.endsWith('/404/') })],
  markdown: {
    processor: unified({
      remarkPlugins: [remarkReadingTime],
      rehypePlugins: [rehypeSlug, rehypeHeadingAnchor, rehypeExternalLinks, rehypeCodeCopyButton],
    }),
    shikiConfig: { themes: { light: 'github-light', dark: 'github-dark' } },
  },
  devToolbar: { enabled: false },
})
