import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
const proxyConfig = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/uploads': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/reports': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/health': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: proxyConfig,
  },
  preview: {
    port: 4175,
    proxy: proxyConfig,
  },
})
