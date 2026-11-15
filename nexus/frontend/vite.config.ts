import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Mirrors nginx.conf's production reverse-proxy behavior, so the frontend's own code can
    // call a plain relative `/api/...` path in both environments — dev talks straight to the
    // uvicorn dev server here, production goes through nginx to the backend container.
    // NEXUS_API_TARGET points the dev server at another backend, for example the deployed one
    // (`NEXUS_API_TARGET=http://k8s-01 npm run dev`), to work on the frontend against live data
    // without running the backend and its Tailscale credentials locally.
    proxy: {
      '/api': process.env.NEXUS_API_TARGET ?? 'http://localhost:8000',
    },
  },
})
