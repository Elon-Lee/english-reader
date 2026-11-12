import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { createHash } from 'node:crypto'

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

// Shared captcha and reader assets remain maintained once; international
// marketing assets live only in public-intl and never enter the domestic build.
function sharedPublicResources(international) {
  if (!international) return { name: 'shiyue-domestic-public' }
  const root = resolve(process.cwd(), 'frontend/public')
  const files = new Map()
  const visit = (directory, prefix = '') => {
    for (const name of readdirSync(directory)) {
      const path = resolve(directory, name)
      const relative = `${prefix}${name}`
      if (statSync(path).isDirectory()) visit(path, `${relative}/`)
      else files.set(`/${relative}`, path)
    }
  }
  visit(root)
  return {
    name: 'shiyue-shared-public',
    generateBundle() {
      for (const [url, path] of files) this.emitFile({ type: 'asset', fileName: url.slice(1), source: readFileSync(path) })
    },
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = files.get(request.url?.split('?')[0])
        if (!path) return next()
        const types = { css: 'text/css', js: 'application/javascript', svg: 'image/svg+xml', png: 'image/png', jpeg: 'image/jpeg' }
        response.setHeader('Content-Type', types[path.split('.').at(-1)] || 'application/octet-stream')
        response.end(readFileSync(path))
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const international = mode === 'intl'
  const site = international ? 'intl' : 'cn'
  return {
  root: resolve(process.cwd(), 'frontend'),
  publicDir: resolve(process.cwd(), international ? 'frontend/public-intl' : 'frontend/public'),
  resolve: { alias: { '@site': resolve(process.cwd(), `frontend/src/sites/${site}/index.jsx`) } },
  plugins: [react(), pdfResources(), sharedPublicResources(international), {
    name: 'shiyue-site-metadata',
    transformIndexHtml(html) {
      if (!international) return html
      return html.replaceAll('纸间微光', 'RynEnglish')
        .replaceAll('记录阅读与学习的点滴。仅向受邀使用者开放的个人阅读空间。', '原声听读、逐句精读与生词复习。选择适合你的学习空间。')
        .replaceAll('https://learn.rynenglish.com/', 'https://10ye.cc/')
        .replaceAll('/brand/paper-glow-mark.svg?v=20261109', '/brand/rynenglish-mark.svg?v=20261106-re2')
    },
  }, {
    name: 'shiyue-entry-cache-version',
    enforce: 'post',
    generateBundle(_, bundle) {
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
    outDir: resolve(process.cwd(), international ? 'reader/site-intl' : 'reader/site'),
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
  }
})
