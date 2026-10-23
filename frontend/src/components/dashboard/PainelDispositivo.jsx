import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ImageOff, X } from 'lucide-react'
import { categoryFromLabel, UNMEASURED } from '../../lib/categories'
import { ehDemo, textoQuando } from '../../lib/dispositivos'

/** Um dispositivo da célula: último frame classificado (só fixa), classe, confiança e horário. */
function ItemDispositivo({ d }) {
  const [falhou, setFalhou] = useState(null)
  const cat = d.captura ? categoryFromLabel(d.captura.weather_label) : UNMEASURED
  const conf = d.captura?.confidence != null ? Math.round(d.captura.confidence * 100) : null
  const semImagem = !d.imagemSrc || falhou === d.imagemSrc
  return (
    <div className="flex flex-col gap-2">
      <div style={{ aspectRatio: '16 / 9', background: 'var(--bg-base)', borderRadius: 8, overflow: 'hidden', position: 'relative' }}>
        {!semImagem ? (
          <img src={d.imagemSrc} alt={`Último frame de ${d.nome}`} onError={() => setFalhou(d.imagemSrc)}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div className="flex flex-col items-center justify-center gap-1 px-4 text-center"
            style={{ height: '100%', color: 'var(--text-secondary)' }}>
            <ImageOff size={20} />
            <span className="font-mono text-xs">
              {d.tipo === 'movel'
                ? 'Imagem do carro não é exibida (privacidade)'
                : d.imagemSrc ? 'Imagem indisponível' : 'Sem captura ainda'}
            </span>
          </div>
        )}
        <span className="font-mono text-xs px-2 py-1 rounded"
          style={{ position: 'absolute', top: 8, left: 8, background: cat.color, color: '#0b1220' }}>
          {cat.label}
        </span>
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{d.nome}</span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          {d.tipo === 'fixa' ? 'Câmera fixa' : 'Veículo'}
          {conf != null && ` · confiança ${conf}%`}
        </span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{textoQuando(d)}</span>
        {ehDemo(d.captura) && (
          <span className="font-mono text-xs" style={{ color: 'var(--cat-moderate)' }}>
            Captura de demonstração (replay), não chuva real
          </span>
        )}
        {d.linkDetalhe && (
          <Link to={d.linkDetalhe} className="font-mono text-xs no-underline" style={{ color: 'var(--accent-brand)' }}>
            {d.tipo === 'fixa' ? 'Ver série das últimas horas →' : 'Ver em Veículos →'}
          </Link>
        )}
      </div>
    </div>
  )
}

/** Painel sobre o mapa com os dispositivos da célula H3 clicada. */
export default function PainelDispositivo({ celula, onFechar }) {
  if (!celula) return null
  return (
    <div className="rounded-xl p-3 flex flex-col gap-3"
      style={{
        position: 'absolute', top: 12, right: 12, zIndex: 1000, width: 300, maxWidth: 'calc(100% - 24px)', maxHeight: 'calc(100% - 24px)',
        overflowY: 'auto', background: 'var(--bg-surface)', border: '1px solid var(--bg-border)',
        boxShadow: '0 8px 24px #0006',
      }}>
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          Célula H3 {celula.celula}
        </span>
        <button type="button" onClick={onFechar} aria-label="Fechar painel"
          style={{ color: 'var(--text-secondary)', background: 'none', border: 0, cursor: 'pointer', padding: 2 }}>
          <X size={16} />
        </button>
      </div>
      {celula.dispositivos.map(d => <ItemDispositivo key={d.chave} d={d} />)}
    </div>
  )
}
