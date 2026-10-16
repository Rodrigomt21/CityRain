import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // TZ fixo: os testes de agrupamento por dia dependem do fuso do dashboard (Brasília)
  test: { environment: 'node', include: ['src/**/*.test.js'], env: { TZ: 'America/Sao_Paulo' } },
})
