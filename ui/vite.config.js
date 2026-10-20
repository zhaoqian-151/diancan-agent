import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  // Read only the non-secret server settings from the backend configuration.
  const serverEnv = loadEnv(mode, resolve(__dirname, '..'), 'SERVER_')
  const apiTarget = process.env.DIANCAN_API_TARGET || `http://127.0.0.1:${serverEnv.SERVER_PORT || 8000}`
  return {
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
  }
})
