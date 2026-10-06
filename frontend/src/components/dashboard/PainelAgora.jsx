import { useEffect, useState } from 'react'
import { CATEGORIES, UNMEASURED, categoryFromLabel, SEVERITY_ORDER } from '../../lib/categories'

const DESCRICAO = {
  dry: 'Sem chuva no vidro.',
  drizzle: 'Precipitação leve (até 2,5 mm/h).',
  moderate: 'Chuva moderada (2,5 a 10 mm/h).',
  heavy: 'Chuva forte (acima de 10 mm/h). Risco de alagamento.',
  unmeasured: 'Captura recebida sem intensidade estimada.',
}
const ORDEM = [...SEVERITY_ORDER].reverse() // seco, garoa, moderada, forte

function haQuanto(data, agora) {
  const s = Math.max(0, Math.round((agora - data) / 1000))
  if (s < 60) return `há ${s} s`
  if (s < 3600) return `há ${Math.round(s / 60)} min`
  if (s < 86400) return `há ${Math.round(s / 3600)} h`
  return `há ${Math.round(s / 86400)} dias`
}

// Rua/bairro da posição atual (Nominatim/OSM), no máximo 1 consulta por posição nova.
function useEndereco(lat, lon) {
  const [end, setEnd] = useState(null)
  useEffect(() => {
    if (lat == null) return
    let cancelado = false
    const t = setTimeout(() => {
      fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=17&lat=${lat}&lon=${lon}`)
        .then(r => r.json())
        .then(d => {
          if (cancelado) return
          const a = d.address ?? {}
          setEnd([a.road, a.suburb ?? a.neighbourhood ?? a.city_district].filter(Boolean).join(' · ') || null)
        })
        .catch(() => {})
    }, 1200)
    return () => { cancelado = true; clearTimeout(t) }
  }, [lat, lon])
  return end
}

export default function PainelAgora({ capturas, ultima, janelaMin }) {
  const [agora, setAgora] = useState(() => new Date())
  useEffect(() => { const id = setInterval(() => setAgora(new Date()), 1000); return () => clearInterval(id) }, [])

  const atual = capturas[capturas.length - 1] ?? null
  const ref = atual ?? ultima
  const cat = ref ? categoryFromLabel(ref.weather_label) : UNMEASURED
  const endereco = useEndereco(ref?.latitude, ref?.longitude)
  const contagem = Object.fromEntries(ORDEM.map(k => [k, 0]))
  capturas.forEach(c => { const k = categoryFromLabel(c.weather_label).key; if (k in contagem) contagem[k] += 1 })
  const total = capturas.length
  const aoVivo = Boolean(atual)

  return (
    <div className="rounded-xl p-5 h-full" style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)', display: 'flex', flexDirection: 'column', gap: 18, overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1.5 }}>AGORA</span>
        <span className="font-mono text-xs px-2 py-0.5 rounded"
          style={{ color: aoVivo ? '#22c55e' : '#94a3b8', background: aoVivo ? '#22c55e1a' : '#94a3b81a', border: `1px solid ${aoVivo ? '#22c55e33' : '#94a3b833'}` }}>
          {aoVivo ? '● AO VIVO' : 'SEM SINAL RECENTE'}
        </span>
      </div>

      {ref ? (
        <div>
          <div className="font-mono font-bold" style={{ fontSize: 44, lineHeight: 1, color: cat.color }}>{cat.label.toUpperCase()}</div>
          <p className="text-sm" style={{ color: 'var(--text-secondary)', margin: '8px 0 0' }}>{DESCRICAO[cat.key]}</p>
          <div className="font-mono text-xs" style={{ color: 'var(--text-secondary)', marginTop: 12, display: 'grid', gridTemplateColumns: '92px 1fr', rowGap: 4 }}>
            <span>confiança</span><span style={{ color: 'var(--text-primary)' }}>{ref.confidence != null ? `${Math.round(ref.confidence * 100)}%` : '—'}</span>
            <span>captura</span><span style={{ color: 'var(--text-primary)' }}>{new Date(ref.captured_at).toLocaleString('pt-BR')} ({haQuanto(new Date(ref.captured_at), agora)})</span>
            <span>local</span><span style={{ color: 'var(--text-primary)' }}>{endereco ?? `${ref.latitude.toFixed(4)}, ${ref.longitude.toFixed(4)}`}</span>
            <span>dispositivo</span><span style={{ color: 'var(--text-primary)' }}>{ref.source_type} #{ref.device_id ?? '—'}{ref.metadata?.demo ? ' · DEMONSTRAÇÃO' : ''}</span>
          </div>
        </div>
      ) : (
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Nenhuma captura recebida ainda.</p>
      )}

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1.5 }}>ÚLTIMOS {janelaMin} MIN</span>
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{total} captura(s)</span>
        </div>
        <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', background: 'var(--bg-border)' }}>
          {ORDEM.map(k => total > 0 && contagem[k] > 0 && (
            <div key={k} style={{ width: `${(100 * contagem[k]) / total}%`, background: CATEGORIES[k].color }} />
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginTop: 10 }}>
          {ORDEM.map(k => (
            <div key={k} className="rounded p-2" style={{ border: '1px solid var(--bg-border)' }}>
              <div className="text-xs font-mono" style={{ color: CATEGORIES[k].color }}>{CATEGORIES[k].label.toUpperCase()}</div>
              <div className="font-mono font-bold" style={{ fontSize: 22, color: 'var(--text-primary)' }}>{contagem[k]}</div>
            </div>
          ))}
        </div>
        {!aoVivo && (
          <p className="text-xs" style={{ color: 'var(--text-secondary)', marginTop: 12 }}>
            Nenhum dispositivo enviou captura nos últimos {janelaMin} min. O mapa mostra a última posição conhecida;
            o trajeto completo está no Histórico.
          </p>
        )}
      </div>

      {capturas.length > 0 && (
        <div>
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1.5 }}>SEQUÊNCIA</span>
          <div style={{ display: 'flex', gap: 2, marginTop: 8, flexWrap: 'wrap' }}>
            {capturas.slice(-60).map(c => (
              <span key={c.id} title={`${new Date(c.captured_at).toLocaleTimeString('pt-BR')} · ${categoryFromLabel(c.weather_label).label}`}
                style={{ width: 8, height: 18, borderRadius: 2, background: categoryFromLabel(c.weather_label).color }} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
