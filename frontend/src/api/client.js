// Cliente HTTP para o backend FastAPI (ml/backend/CLAUDE.md > Stack de Backend)
// VITE_API_URL aponta o dashboard para outra API (ex.: backend local em testes ponta a ponta)
export const BASE_URL = import.meta.env.VITE_API_URL ?? 'https://api-production-046f.up.railway.app'

export async function apiGet(path) {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
