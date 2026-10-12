import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig({
  root: resolve(process.cwd(), 'frontend'),
  plugins: [react()],
  base: '/',
  server: {
    host: '127.0.0.1',
    port: 5173,
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
        chunkFileNames: 'assets/[name].js',
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
