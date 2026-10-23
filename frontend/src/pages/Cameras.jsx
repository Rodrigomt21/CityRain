import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import Topbar from '../components/layout/Topbar'
import CameraCard from '../components/cameras/CameraCard'
import { CameraCardSkeleton } from '../components/Skeleton'
import { useCameras } from '../hooks/useCameras'
import { resumoCamera } from '../lib/cameras'
import { NOME_TIPO } from '../lib/dispositivos'
import { BASE_URL } from '../api/client'

/** Grade das câmeras fixas, classificadas pelo modelo fixo, atualizando sozinha. */
export default function Cameras() {
  const { cameras, error, carregando, pollMs } = useCameras()
  const resumos = useMemo(() => cameras.map(c => resumoCamera(c, BASE_URL)), [cameras])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb={NOME_TIPO.fixa} backTo="/dashboard" />
      <main className="p-3 md:p-6 flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-mono font-bold" style={{ fontSize: '22px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}>
              {NOME_TIPO.fixa}
            </h1>
            <p className="text-sm" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Transmissões públicas classificadas pelo modelo de câmera fixa · atualiza a cada {Math.round(pollMs / 1000)} s
            </p>
          </div>
          <Link to="/dashboard?tipo=fixa" className="font-mono text-xs px-3 py-1.5 rounded no-underline"
            style={{ color: 'var(--accent-brand)', background: '#3b82f61a', border: '1px solid #3b82f633', whiteSpace: 'nowrap' }}>
            Ver no mapa →
          </Link>
        </div>
        {error && <p className="font-mono text-xs" style={{ color: 'var(--cat-heavy)' }}>Não consegui falar com a API ({error.message}). Tento de novo no próximo ciclo.</p>}
        {!carregando && !error && resumos.length === 0 && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Nenhuma câmera fixa cadastrada.</p>
        )}
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
          {carregando && (
            <div role="status" aria-label="Carregando câmeras" style={{ display: 'contents' }}>
              {Array.from({ length: 6 }, (_, i) => <CameraCardSkeleton key={i} />)}
            </div>
          )}
          {resumos.map(r => <CameraCard key={r.id} r={r} />)}
        </div>
        <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: 0 }}>
          As câmeras embarcadas no carro ficam em{' '}
          <Link to="/dispositivos" className="no-underline" style={{ color: 'var(--accent-brand)' }}>{NOME_TIPO.movel} →</Link>
        </p>
      </main>
    </div>
  )
}
