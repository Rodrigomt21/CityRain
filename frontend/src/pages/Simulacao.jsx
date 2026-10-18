import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapContainer, TileLayer, Polygon, CircleMarker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { AlertTriangle, Pause, Play, RotateCcw } from 'lucide-react'
import { CATEGORIES } from '../lib/categories'
import { celulasCidade, criarSensores, estimarCidade, leituras, porBairro, posicaoCarro } from '../lib/simulacao'

// Visão de futuro (defesa): frota de carros + câmeras fixas cobrindo São Paulo. SIMULAÇÃO ILUSTRATIVA:
// a chuva e as leituras são geradas no navegador; nada vem da API nem vai para o banco.

const PASSO_S = 15        // segundos simulados por quadro
const QUADRO_MS = 300     // ~50 s simulados por segundo real: a tempestade cruza a cidade em ~1 min
const INICIO_H = 16       // relógio simulado começa às 16:00
const ORDEM = ['heavy', 'moderate', 'drizzle', 'dry']

function horaSimulada(t) {
  const min = INICIO_H * 60 + Math.floor(t / 60)
  return `${String(Math.floor(min / 60) % 24).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`
}

function Bairros({ lista }) {
  const max = Math.max(1, ...lista.map(b => b.mm ?? 0))
  return (
    <div style={{ flex: 1, minHeight: 0, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 16, padding: '14px 16px', overflow: 'hidden' }}>
      <div className="font-mono" style={{ fontSize: 12, letterSpacing: 1.5, color: 'var(--text-secondary)', marginBottom: 8 }}>QUANTO CHOVE EM CADA BAIRRO</div>
      {lista.map(b => (
        <div key={b.nome} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0' }}>
          <span style={{ width: 112, fontSize: 14, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{b.nome}</span>
          <div style={{ flex: 1, height: 10, borderRadius: 5, background: 'var(--bg-border)', overflow: 'hidden' }}>
            <div style={{ width: `${b.mm == null ? 0 : Math.max(2, (100 * b.mm) / max)}%`, height: '100%',
              background: b.categoria?.color ?? 'transparent', transition: 'width 0.3s, background 0.3s' }} />
          </div>
          <span className="font-mono" style={{ width: 168, textAlign: 'right', fontSize: 13, whiteSpace: 'nowrap', color: b.categoria?.color ?? 'var(--text-secondary)' }}>
            {b.mm == null ? 'sem sensor perto' : `${b.categoria.label} · ${b.mm.toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })} mm/h`}
          </span>
        </div>
      ))}
    </div>
  )
}

function Kpi({ rotulo, valor, detalhe, cor }) {
  return (
    <div style={{ flex: 1, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 12, padding: '10px 14px' }}>
      <div className="font-mono" style={{ fontSize: 11, letterSpacing: 1.5, color: 'var(--text-secondary)' }}>{rotulo}</div>
      <div className="font-mono font-bold" style={{ fontSize: 28, color: cor ?? 'var(--text-primary)', lineHeight: 1.15 }}>{valor}</div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{detalhe}</div>
    </div>
  )
}

export default function Simulacao() {
  const [nCarros, setNCarros] = useState(120)
  const [t, setT] = useState(300)
  const [rodando, setRodando] = useState(true)
  const celulas = useMemo(() => celulasCidade(), [])
  const nCameras = Math.round(nCarros / 4)
  const sensores = useMemo(() => criarSensores(nCarros, nCameras), [nCarros, nCameras])

  useEffect(() => {
    if (!rodando) return undefined
    const id = setInterval(() => setT(v => (v >= 3900 ? 0 : v + PASSO_S)), QUADRO_MS)
    return () => clearInterval(id)
  }, [rodando])

  const leit = useMemo(() => leituras(sensores, t), [sensores, t])
  const cidade = useMemo(() => estimarCidade(celulas, leit, t), [celulas, leit, t])
  const bairros = useMemo(() => porBairro(leit), [leit])
  const carros = useMemo(() => sensores.carros.map(c => ({ id: c.id, ...posicaoCarro(c, t) })), [sensores, t])
  const alerta = bairros.filter(b => b.categoria === CATEGORIES.heavy).map(b => b.nome)

  return (
    <div style={{ height: '100vh', background: 'radial-gradient(1200px 600px at 70% -10%, #7c3aed22, transparent), var(--bg-base)',
      display: 'flex', flexDirection: 'column', padding: '16px 24px', gap: 12, overflow: 'hidden' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <Link to="/apresentacao" className="no-underline" style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span className="font-mono font-bold" style={{ fontSize: 28, color: 'var(--text-primary)' }}>City<span style={{ color: 'var(--accent-brand)' }}>Rain</span></span>
          <span style={{ fontSize: 15, color: 'var(--text-secondary)' }}>a cidade conectada: cada carro e cada câmera viram um pluviômetro</span>
        </Link>
        <div style={{ flex: 1 }} />
        <span className="font-mono" style={{ fontSize: 13, letterSpacing: 1.5, padding: '6px 12px', borderRadius: 999,
          color: '#c4b5fd', border: '1px solid #8b5cf666', background: '#8b5cf61a' }}>
          SIMULAÇÃO ILUSTRATIVA · dados gerados, não medidos
        </span>
        <span className="font-mono" style={{ fontSize: 26, color: 'var(--text-primary)' }}>{horaSimulada(t)}</span>
      </header>

      <div style={{ display: 'flex', gap: 12 }}>
        <Kpi rotulo="CARROS NA RUA" valor={nCarros} detalhe="Jetson no para-brisa" />
        <Kpi rotulo="CÂMERAS FIXAS" valor={nCameras} detalhe="CCTV e lives públicas" />
        <Kpi rotulo="CIDADE COBERTA" valor={`${cidade.coberturaPct}%`} detalhe="células H3 com sensor a até 2,5 km" cor="#60a5fa" />
        <Kpi rotulo="ACERTO DA CLASSE" valor={`${cidade.acertoPct}%`} detalhe="contra a chuva simulada, cidade inteira" cor="#4ade80" />
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 14 }}>
        <div style={{ flex: 1, minWidth: 0, borderRadius: 16, overflow: 'hidden', border: '1px solid var(--bg-border)', position: 'relative' }}>
          <MapContainer center={[-23.575, -46.625]} zoom={12} preferCanvas zoomControl={false}
            style={{ height: '100%', width: '100%', background: '#0b1220' }}>
            <TileLayer className="mapa-escuro" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {cidade.estimadas.map(c => c.categoria && c.categoria !== CATEGORIES.dry && (
              <Polygon key={c.h} positions={c.contorno} interactive={false}
                pathOptions={{ stroke: false, fillColor: c.categoria.color, fillOpacity: 0.45 }} />
            ))}
            {sensores.cameras.map(cam => (
              <CircleMarker key={cam.id} center={[cam.lat, cam.lng]} radius={4} interactive={false}
                pathOptions={{ color: '#e9d5ff', weight: 1.5, fillColor: '#8b5cf6', fillOpacity: 1 }} />
            ))}
            {carros.map(c => (
              <CircleMarker key={c.id} center={[c.lat, c.lng]} radius={3.5} interactive={false}
                pathOptions={{ color: '#0b1220', weight: 1, fillColor: '#f8fafc', fillOpacity: 1 }} />
            ))}
          </MapContainer>
          <div className="font-mono" style={{ position: 'absolute', left: 12, bottom: 22, zIndex: 1000, pointerEvents: 'none',
            background: 'rgba(11, 18, 32, 0.88)', border: '1px solid var(--bg-border)', borderRadius: 8, padding: '8px 10px', fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.6 }}>
            {ORDEM.slice(0, 3).map(k => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: CATEGORIES[k].color }} />{CATEGORIES[k].label} (célula H3 ~460 m)
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ width: 8, height: 8, borderRadius: 4, background: '#f8fafc' }} />carro</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ width: 8, height: 8, borderRadius: 4, background: '#8b5cf6' }} />câmera fixa</div>
          </div>
        </div>

        <div style={{ width: 470, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 16, padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button type="button" onClick={() => setRodando(r => !r)} aria-label={rodando ? 'Pausar' : 'Continuar'}
                style={{ width: 40, height: 40, borderRadius: 10, display: 'grid', placeItems: 'center', cursor: 'pointer',
                  background: 'var(--accent-brand)', color: '#fff', border: 'none' }}>
                {rodando ? <Pause size={18} /> : <Play size={18} />}
              </button>
              <button type="button" onClick={() => setT(0)} aria-label="Recomeçar"
                style={{ width: 40, height: 40, borderRadius: 10, display: 'grid', placeItems: 'center', cursor: 'pointer',
                  background: 'transparent', color: 'var(--text-primary)', border: '1px solid var(--bg-border)' }}>
                <RotateCcw size={18} />
              </button>
              <div style={{ flex: 1 }}>
                <label htmlFor="frota" className="font-mono" style={{ fontSize: 12, color: 'var(--text-secondary)', letterSpacing: 1 }}>
                  TAMANHO DA FROTA: {nCarros} carros + {nCameras} câmeras
                </label>
                <input id="frota" type="range" min={5} max={200} step={5} value={nCarros}
                  onChange={e => setNCarros(Number(e.target.value))} style={{ width: '100%', accentColor: '#3b82f6' }} />
              </div>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0 0', lineHeight: 1.45 }}>
              Arraste a frota: com poucos carros a cidade fica às cegas; com muitos, cada célula de ~460 m ganha uma estimativa.
              Hoje há algumas dezenas de pluviômetros públicos para toda a cidade.
            </p>
          </div>

          {alerta.length > 0 && (
            <div className="ap-entrar" style={{ display: 'flex', alignItems: 'center', gap: 10, borderRadius: 14, padding: '12px 14px',
              background: '#ef44441f', border: '1px solid #ef444477', color: '#fecaca' }}>
              <AlertTriangle size={20} color="#ef4444" />
              <span style={{ fontSize: 15 }}><b>Alerta de chuva forte:</b> {alerta.slice(0, 4).join(', ')}{alerta.length > 4 ? ` e mais ${alerta.length - 4}` : ''}</span>
            </div>
          )}

          <Bairros lista={bairros} />
        </div>
      </div>
    </div>
  )
}
