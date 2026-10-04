// Cliente HTTP para o backend FastAPI (ml/backend/CLAUDE.md > Stack de Backend)
export const BASE_URL = 'https://api-production-046f.up.railway.app'

export async function apiGet(path) {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
