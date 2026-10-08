import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

const POLL_MS = Number(import.meta.env.VITE_POLL_MS) || 30_000

/** Série de classes de uma câmera fixa nas últimas `horas` (GET /api/v1/cameras/{id}/serie). */
export function useSerieCamera(id, horas) {
  const [estado, setEstado] = useState({ chave: null, serie: [], agora: null, erro: null })
  const chave = `${id}:${horas}`

  useEffect(() => {
    let cancelado = false
    const buscar = () =>
      apiGet(`/api/v1/cameras/${id}/serie?horas=${horas}`)
        .then(d => { if (!cancelado) { setEstado({ chave, serie: d, agora: Date.now(), erro: null }) } })
        .catch(e => { if (!cancelado) setEstado(ant => ({ ...ant, chave, erro: e, ...(ant.chave === chave ? {} : { serie: [], agora: null }) })) })
    buscar()
    const t = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(t) }
  }, [id, horas, chave])

  // Dados e erro de outra janela/câmera não valem: enquanto a nova não chega, "carregando".
  const atual = estado.chave === chave
  const error = atual ? estado.erro : null
  return { serie: atual ? estado.serie : [], agora: atual ? estado.agora : null, error, carregando: !atual || (estado.agora === null && !error) }
}
