// Cliente HTTP para o backend FastAPI (ml/backend/CLAUDE.md > Stack de Backend)
// VITE_API_URL aponta o dashboard para outra API (ex.: backend local em testes ponta a ponta)
export const BASE_URL = import.meta.env.VITE_API_URL ?? 'https://api-production-046f.up.railway.app'

// Carrega o status HTTP junto do erro: a UI precisa distinguir 401 (falta chave)
// de uma falha qualquer, para pedir configuração em vez de mostrar "erro".
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * GET no backend, opcionalmente autenticado por Bearer token.
 *
 * Leituras do dashboard (capturas, mapa de calor) são públicas e não passam
 * `token`. Endpoints administrativos (hoje só GET /devices/) exigem a chave
 * de admin (ver backend/app/core/security.py:verificar_admin_key).
 */
export async function apiGet(path, { token } = {}) {
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined

  // Falha de rede (Wi-Fi oscilando, roteador do celular): tenta de novo uma vez antes de acusar erro,
  // para uma piscada da conexão não virar "API indisponível" na tela.
  let res
  for (let tentativa = 0; ; tentativa++) {
    try {
      res = await fetch(`${BASE_URL}${path}`, { headers })
      break
    } catch {
      if (tentativa >= 1) throw new ApiError('Falha de rede ao conectar à API.', 0)
      await new Promise(r => setTimeout(r, 1500))
    }
  }

  if (!res.ok) {
    throw new ApiError(`GET ${path} failed: ${res.status} ${res.statusText}`, res.status)
  }
  return res.json()
}
