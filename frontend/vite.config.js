import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端默认 http://127.0.0.1:8000；开发时经 /api 与 /ws 代理
const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  base: './', // 打包后可由任意静态服务器/FastAPI 托管
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
  },
})
