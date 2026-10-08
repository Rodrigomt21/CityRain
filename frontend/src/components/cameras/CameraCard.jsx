import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ImageOff } from 'lucide-react'

/** Card de uma câmera fixa: miniatura, classe do modelo, confiança e há quanto tempo. */
export default function CameraCard({ r }) {
  const [falhou, setFalhou] = useState(null)
  const semImagem = falhou === r.imagemSrc
  return (
    <Link to={`/cameras/${r.id}`} className="rounded-xl overflow-hidden flex flex-col"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)' }}>
      <div style={{ aspectRatio: '4 / 3', background: 'var(--bg-base)', position: 'relative' }}>
        {r.imagemSrc && !semImagem ? (
          <img src={r.imagemSrc} alt="" onError={() => setFalhou(r.imagemSrc)}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div className="flex flex-col items-center justify-center gap-1" style={{ height: '100%', color: 'var(--text-secondary)' }}>
            <ImageOff size={20} />
            <span className="font-mono text-xs">{r.imagemSrc ? 'imagem indisponível' : 'sem captura ainda'}</span>
          </div>
        )}
        <span className="font-mono text-xs px-2 py-1 rounded"
          style={{ position: 'absolute', top: 8, left: 8, background: r.categoria.color, color: '#0b1220' }}>
          {r.categoria.label}
        </span>
      </div>
      <div className="p-3 flex flex-col gap-1">
        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{r.nome}</span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          {r.quando}{r.confiancaPct != null && ` · confiança ${r.confiancaPct}%`}{r.aoVivo && ' · ao vivo'}
        </span>
      </div>
    </Link>
  )
}
