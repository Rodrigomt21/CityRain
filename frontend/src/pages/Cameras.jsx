import { useMemo } from 'react'
import Topbar from '../components/layout/Topbar'
import CameraCard from '../components/cameras/CameraCard'
import { useCameras } from '../hooks/useCameras'
import { resumoCamera } from '../lib/cameras'
import { BASE_URL } from '../api/client'

/** Grade das câmeras fixas, classificadas pelo modelo fixo, atualizando sozinha. */
export default function Cameras() {
  const { cameras, error, carregando, pollMs } = useCameras()
  const resumos = useMemo(() => cameras.map(c => resumoCamera(c, BASE_URL)), [cameras])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb="Câmeras fixas" backTo="/dashboard" />
      <main className="p-6 flex flex-col gap-4">
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Transmissões públicas classificadas pelo modelo de câmera fixa · atualiza a cada {Math.round(pollMs / 1000)} s
        </p>
        {error && <p className="font-mono text-xs" style={{ color: 'var(--cat-heavy)' }}>Não consegui falar com a API ({error.message}). Tento de novo no próximo ciclo.</p>}
        {carregando && <p className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Carregando…</p>}
        {!carregando && !error && resumos.length === 0 && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Nenhuma câmera fixa cadastrada.</p>
        )}
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
          {resumos.map(r => <CameraCard key={r.id} r={r} />)}
        </div>
      </main>
    </div>
  )
}
