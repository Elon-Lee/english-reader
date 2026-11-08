import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { readFileSync, readdirSync } from 'node:fs'
import { createHash } from 'node:crypto'

const homepageImages = ['reader-lookup-20261026.webp', 'reader-tools-20261026.webp', 'workspace-current.jpg', 'vocabulary-review-20261026.webp']

// Self-host PDF fonts, CMaps and image decoders, including offline Linux installs.
function pdfResources() {
  const version = JSON.parse(readFileSync(resolve(process.cwd(), 'node_modules/pdfjs-dist/package.json'), 'utf8')).version
  const assets = new Map(['cmaps', 'standard_fonts', 'wasm'].flatMap(directory => {
    const root = resolve(process.cwd(), 'node_modules/pdfjs-dist', directory)
    return readdirSync(root).map(name => [`/pdf-assets/${version}/${directory}/${name}`, resolve(root, name)])
  }))
  return {
    name: 'shiyue-pdf-resources',
    generateBundle() { for (const [url, path] of assets) this.emitFile({ type: 'asset', fileName: url.slice(1), source: readFileSync(path) }) },
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const file = assets.get(request.url?.split('?')[0])
        if (!file) return next()
        response.setHeader('Content-Type', file.endsWith('.wasm') ? 'application/wasm' : file.endsWith('.js') ? 'application/javascript' : 'application/octet-stream')
        response.end(readFileSync(file))
      })
    },
  }
}

export default defineConfig({
  root: resolve(process.cwd(), 'frontend'),
  plugins: [react(), pdfResources(), {
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
    port: 4173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8790',
        changeOrigin: false,
      },
      '/books': {
        target: 'http://127.0.0.1:8790',
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
          if (id.endsWith('/components/useBookPageTurn.jsx')) return 'bookPageTurn'
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/pdfjs-dist/')) return 'pdfjs'
          if (['/fflate/', '/dompurify/', '/css-tree/', '/mdn-data/', '/source-map-js/'].some(name => id.includes(name))) return 'epub'
          if (id.includes('/antd/')) return 'antd'
          if (id.includes('/@ant-design/icons')) return 'icons'
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) return 'react'
          return 'vendor'
        },
      },
    },
  },
})
