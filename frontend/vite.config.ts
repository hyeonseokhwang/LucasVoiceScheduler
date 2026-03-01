import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:7778',
        changeOrigin: true,
      },
      '/api/schedules/ws': {
        target: 'ws://localhost:7778',
        ws: true,
      },
    },
  },
})
