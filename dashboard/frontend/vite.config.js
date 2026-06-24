import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 프론트(8166)는 /api 를 백엔드(8165)로 프록시 → 외부 노출은 8166 한 포트만.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 8166,
    proxy: { '/api': 'http://127.0.0.1:8165' },
  },
})
