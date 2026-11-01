import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Lets shadcn/ui components import from "@/components/ui/...".
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // In development, forward API calls to Django so the browser sees one origin (no CORS setup).
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
