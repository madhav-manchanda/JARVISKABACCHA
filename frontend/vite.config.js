import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://127.0.0.1:8002',
      '/command': 'http://127.0.0.1:8002',
      '/memory': 'http://127.0.0.1:8002',
      '/contacts': 'http://127.0.0.1:8002',
      '/health': 'http://127.0.0.1:8002',
      '/timers': 'http://127.0.0.1:8002',
      '/audio': 'http://127.0.0.1:8002',
      '/homework': 'http://127.0.0.1:8002',
      '/downloads': 'http://127.0.0.1:8002',
      '/ws': {
        target: 'ws://127.0.0.1:8002',
        ws: true,
      },
    },
  },
})
