import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev the React server runs on 5173 and proxies /api to uvicorn on 8000.
// In production there is no proxy: FastAPI serves this build from the same
// origin, which is why the app can use relative /api paths everywhere and
// needs no CORS configuration at all.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
