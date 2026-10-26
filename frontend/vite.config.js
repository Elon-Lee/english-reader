import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

const homepageImages = ['reader-word-panel.jpg', 'workspace-current.jpg', 'learning-insights.png']

export default defineConfig({
  root: resolve(process.cwd(), 'frontend'),
  plugins: [react(), {
    name: 'shiyue-entry-cache-version',
    enforce: 'post',
    generateBundle(_, bundle) {
      for (const asset of Object.values(bundle)) {
        if (asset.type !== 'chunk') continue
        for (const filename of homepageImages) {
          const imagePath = resolve(process.cwd(), 'frontend/public/product', filename)
          const version = createHash('sha256').update(readFileSync(imagePath)).digest('hex').slice(0, 12)
          asset.code = asset.code.replaceAll(`/product/${filename}`, `/product/${filename}?v=${version}`)
        }
      }
      const entry = bundle['index.html']
      if (!entry) return
      entry.source = String(entry.source).replace(/(\/assets\/(?:index\.js|index\.css))(?=["'])/g, (url) => {
        const asset = bundle[url.slice(1)]
        if (!asset) return url
        const version = createHash('sha256').update(asset.code ?? asset.source).digest('hex').slice(0, 12)
        return `${url}?v=${version}`
      })
    },
  }],
  base: '/',
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.SHIYUE_API_PROXY_TARGET || 'http://127.0.0.1:8790',
        changeOrigin: false,
      },
      '/books': {
        target: process.env.SHIYUE_API_PROXY_TARGET || 'http://127.0.0.1:8790',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: resolve(process.cwd(), 'reader/site'),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(process.cwd(), 'frontend/index.html'),
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name][extname]',
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/antd/')) return 'antd'
          if (id.includes('/@ant-design/icons')) return 'icons'
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) return 'react'
          return 'vendor'
        },
      },
    },
  },
})
