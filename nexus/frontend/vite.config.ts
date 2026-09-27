import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Mirrors nginx.conf's production reverse-proxy behavior, so the frontend's own code can
    // call a plain relative `/api/...` path in both environments — dev talks straight to the
    // uvicorn dev server here, production goes through nginx to the backend container.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
