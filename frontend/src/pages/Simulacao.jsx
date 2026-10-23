import { useEffect, useMemo, useState } from 'react'
import Topbar from '../components/layout/Topbar'
import { MapContainer, TileLayer, Polygon, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { AlertTriangle, Car, Pause, Play, RotateCcw } from 'lucide-react'
import { CATEGORIES } from '../lib/categories'
import { celulasCidade, criarPluviometros, criarSensores, estimarCidade, leituras, porBairro, posicaoCarro } from '../lib/simulacao'

// Visão de futuro: frota de carros + câmeras fixas cobrindo São Paulo. SIMULAÇÃO ILUSTRATIVA:
// a chuva e as leituras são geradas no navegador; nada vem da API nem vai para o banco.
// Abre em "hoje" (só os pluviômetros públicos reais) e o visitante conecta a frota com um toque:
// o contraste entre as duas situações é o argumento do projeto.

const PASSO_S = 15        // segundos simulados por quadro
const QUADRO_MS = 300     // ~50 s simulados por segundo real: a tempestade cruza a cidade em ~1 min
const INICIO_H = 16       // relógio simulado começa às 16:00
const ORDEM = ['heavy', 'moderate', 'drizzle', 'dry']
const FROTA_ALVO = 120    // carros ao tocar "Conectar a frota"
const ENTRADA_MS = 90     // a frota entra de 5 em 5 carros: ~2 s até o alvo
const COR_PLUVIOMETRO = '#fbbf24'

function horaSimulada(t) {
  const min = INICIO_H * 60 + Math.floor(t / 60)
  return `${String(Math.floor(min / 60) % 24).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`
}

/** mm/h com 1 casa; chuva acima de zero que arredondaria para 0,0 vira "< 0,1" (garoa 0,0 mm/h confundia). */
function formatarMm(mm) {
  if (mm > 0 && mm < 0.05) return '< 0,1'
  return mm.toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })
}

function Bairros({ lista }) {
  const max = Math.max(1, ...lista.map(b => b.mm ?? 0))
  return (
    <div style={{ flex: 1, minHeight: 0, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 12, padding: '14px 16px', overflow: 'hidden' }}>
      <div className="font-mono" style={{ fontSize: 12, letterSpacing: 1.5, color: 'var(--text-secondary)', marginBottom: 8 }}>QUANTO CHOVE EM CADA BAIRRO</div>
      {lista.map(b => (
        <div key={b.nome} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0' }}>
          <span style={{ width: 112, flexShrink: 0, fontSize: 14, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.nome}</span>
          <div style={{ flex: 1, height: 10, borderRadius: 5, background: 'var(--bg-border)', overflow: 'hidden' }}>
            <div style={{ width: `${b.mm == null ? 0 : Math.max(2, (100 * b.mm) / max)}%`, height: '100%',
              background: b.categoria?.color ?? 'transparent', transition: 'width 0.3s, background 0.3s' }} />
          </div>
          <span className="font-mono w-[140px] md:w-[168px] shrink-0" style={{ textAlign: 'right', fontSize: 13, whiteSpace: 'nowrap', color: b.categoria?.color ?? 'var(--text-secondary)' }}>
            {b.mm == null ? 'sem sensor perto' : `${b.categoria.label} · ${formatarMm(b.mm)} mm/h`}
          </span>
        </div>
      ))}
    </div>
  )
}

function Kpi({ rotulo, valor, detalhe, cor }) {
  return (
    <div style={{ flex: 1, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 12, padding: '10px 14px' }}>
      <div className="font-mono" style={{ fontSize: 12, letterSpacing: 1.5, color: 'var(--text-secondary)' }}>{rotulo}</div>
      <div className="font-mono font-bold" style={{ fontSize: 28, color: cor ?? 'var(--text-primary)', lineHeight: 1.15 }}>{valor}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{detalhe}</div>
    </div>
  )
}

function Legenda() {
  const item = (cor, texto, redondo) => (
    <div key={texto} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 10, height: 10, borderRadius: redondo ? 5 : 2, background: cor, flexShrink: 0 }} />{texto}
    </div>
  )
  return (
    <div className="font-mono flex flex-wrap md:block gap-x-3" style={{ position: 'absolute', left: 10, top: 10, zIndex: 1000, pointerEvents: 'none',
      maxWidth: 'calc(100% - 20px)', background: 'rgba(11, 18, 32, 0.88)', border: '1px solid var(--bg-border)', borderRadius: 8,
      padding: '6px 10px', fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.6 }}>
      {ORDEM.slice(0, 3).map(k => item(CATEGORIES[k].color, CATEGORIES[k].label))}
      {item(COR_PLUVIOMETRO, 'pluviômetro', true)}
      {item('#f8fafc', 'carro', true)}
      {item('#8b5cf6', 'câmera fixa', true)}
    </div>
  )
}

/** Cartão sobre o mapa enquanto a cidade só tem pluviômetros: o convite para conectar a frota. */
function ConviteConectar({ nPluviometros, onConectar }) {
  return (
    <div className="ap-entrar" style={{ position: 'absolute', left: 12, right: 12, bottom: 28, zIndex: 1000, display: 'flex', justifyContent: 'center' }}>
      <div style={{ maxWidth: 420, width: '100%', background: 'rgba(11, 18, 32, 0.94)', border: '1px solid var(--bg-border)', borderRadius: 14,
        padding: '14px 16px', boxShadow: '0 8px 24px #0008', textAlign: 'center' }}>
        <div className="font-mono" style={{ fontSize: 12, letterSpacing: 1.5, color: COR_PLUVIOMETRO }}>HOJE</div>
        <p style={{ fontSize: 15, color: 'var(--text-primary)', margin: '4px 0 12px', lineHeight: 1.45 }}>
          Só {nPluviometros} pluviômetros medem a chuva nesta área. Onde não tem um perto, o mapa fica às cegas.
        </p>
        <button type="button" onClick={onConectar}
          className="font-mono font-semibold"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 22px', borderRadius: 10, fontSize: 15,
            background: 'var(--accent-brand)', color: '#fff', border: 'none', cursor: 'pointer', boxShadow: '0 0 24px #3b82f655' }}>
          <Car size={18} /> Conectar a frota
        </button>
      </div>
    </div>
  )
}

export default function Simulacao() {
  const [nCarros, setNCarros] = useState(0)
  const [conectando, setConectando] = useState(false)
  const [t, setT] = useState(0)
  const [rodando, setRodando] = useState(true)
  const celulas = useMemo(() => celulasCidade(), [])
  const pluviometros = useMemo(() => criarPluviometros(), [])
  const nCameras = Math.round(nCarros / 4)
  const sensores = useMemo(() => criarSensores(nCarros, nCameras), [nCarros, nCameras])
  const hoje = nCarros === 0 && !conectando

  useEffect(() => {
    if (!rodando) return undefined
    const id = setInterval(() => setT(v => (v >= 3900 ? 0 : v + PASSO_S)), QUADRO_MS)
    return () => clearInterval(id)
  }, [rodando])

  // entrada da frota: carros aparecem aos poucos até FROTA_ALVO (o intervalo para sozinho ao chegar lá)
  const entrando = conectando && nCarros < FROTA_ALVO
  useEffect(() => {
    if (!entrando) return undefined
    const id = setInterval(() => setNCarros(n => Math.min(FROTA_ALVO, n + 5)), ENTRADA_MS)
    return () => clearInterval(id)
  }, [entrando])

  const conectar = () => { setRodando(true); setConectando(true) }
  const recomecar = () => { setConectando(false); setNCarros(0); setT(0); setRodando(true) }

  const leit = useMemo(() => leituras(sensores, t, pluviometros), [sensores, t, pluviometros])
  const cidade = useMemo(() => estimarCidade(celulas, leit, t), [celulas, leit, t])
  const bairros = useMemo(() => porBairro(leit), [leit])
  const carros = useMemo(() => sensores.carros.map(c => ({ id: c.id, ...posicaoCarro(c, t) })), [sensores, t])
  const alerta = bairros.filter(b => b.categoria === CATEGORIES.heavy).map(b => b.nome)

  return (
    <div className="min-h-screen md:h-screen flex flex-col md:overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <Topbar breadcrumb="Simulação" backTo="/apresentacao" />
      <main className="flex-1 min-h-0 flex flex-col gap-3 px-3 py-3 md:px-5 md:py-4">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 className="font-mono font-bold" style={{ fontSize: 22, color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}>
            {hoje ? 'A cidade hoje' : 'A cidade conectada'}
          </h1>
          <p className="text-[13px]" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
            {hoje ? 'Só os pluviômetros públicos medem a chuva' : 'Cada carro e cada câmera viram um pluviômetro'} · relógio simulado {horaSimulada(t)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <span className="font-mono text-xs px-2 py-0.5 rounded"
            style={{ color: '#fbbf24', background: '#fbbf241a', border: '1px solid #fbbf2433' }}>
            SIMULAÇÃO ILUSTRATIVA · dados gerados, não medidos
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:flex gap-3">
        <Kpi rotulo="PLUVIÔMETROS" valor={pluviometros.length} detalhe="reais nesta área: CEMADEN, CGE e INMET" cor={COR_PLUVIOMETRO} />
        <Kpi rotulo="FROTA" valor={nCarros + nCameras} detalhe={`${nCarros} carros + ${nCameras} câmeras`} />
        <Kpi rotulo="CIDADE COBERTA" valor={`${cidade.coberturaPct}%`} detalhe="área com sensor a até 1,5 km" cor="#60a5fa" />
        <Kpi rotulo="CHUVA FORTE VISTA" valor={cidade.fortePct == null ? '—' : `${cidade.fortePct}%`}
          detalhe={cidade.fortePct == null ? 'sem chuva forte neste momento' : 'da área com chuva forte simulada'} cor="#f87171" />
      </div>

      <div className="flex flex-col md:flex-row gap-3.5 flex-1 min-h-0">
        <div className="md:flex-1 min-w-0 h-[60vh] md:h-auto" style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--bg-border)', position: 'relative' }}>
          <MapContainer center={[-23.575, -46.625]} zoom={12} preferCanvas zoomControl={false}
            style={{ height: '100%', width: '100%', background: '#0b1220' }}>
            <TileLayer className="mapa-escuro" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {cidade.estimadas.map(c => c.categoria && c.categoria !== CATEGORIES.dry && (
              <Polygon key={c.h} positions={c.contorno} interactive={false}
                pathOptions={{ stroke: false, fillColor: c.categoria.color, fillOpacity: 0.45 }} />
            ))}
            {pluviometros.map(p => (
              <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={4.5}
                pathOptions={{ color: '#0b1220', weight: 1.5, fillColor: COR_PLUVIOMETRO, fillOpacity: 1 }}>
                <Tooltip>{p.fonte} · {p.nome}{p.aprox ? ' (posição aproximada)' : ''}</Tooltip>
              </CircleMarker>
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
          <Legenda />
          {hoje && <ConviteConectar nPluviometros={pluviometros.length} onConectar={conectar} />}
        </div>

        <div className="w-full md:w-[470px] shrink-0 flex flex-col gap-3 min-h-0">
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 12, padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button type="button" onClick={() => setRodando(r => !r)} aria-label={rodando ? 'Pausar' : 'Continuar'}
                style={{ width: 44, height: 44, borderRadius: 10, display: 'grid', placeItems: 'center', cursor: 'pointer',
                  background: 'var(--accent-brand)', color: '#fff', border: 'none', flexShrink: 0 }}>
                {rodando ? <Pause size={18} /> : <Play size={18} />}
              </button>
              <button type="button" onClick={recomecar} aria-label="Recomeçar do zero (só pluviômetros)" title="Recomeçar do zero"
                style={{ width: 44, height: 44, borderRadius: 10, display: 'grid', placeItems: 'center', cursor: 'pointer',
                  background: 'transparent', color: 'var(--text-primary)', border: '1px solid var(--bg-border)', flexShrink: 0 }}>
                <RotateCcw size={18} />
              </button>
              <div style={{ flex: 1, minWidth: 0 }}>
                <label htmlFor="frota" className="font-mono" style={{ fontSize: 12, color: 'var(--text-secondary)', letterSpacing: 1 }}>
                  TAMANHO DA FROTA: {nCarros} carros + {nCameras} câmeras
                </label>
                <input id="frota" type="range" min={0} max={200} step={5} value={nCarros}
                  onChange={e => { setConectando(false); setNCarros(Number(e.target.value)) }} style={{ width: '100%', accentColor: '#3b82f6' }} />
              </div>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0 0', lineHeight: 1.45 }}>
              Arraste a frota: com poucos carros a cidade fica às cegas; com muitos, cada célula de ~460 m ganha uma estimativa.
              Hoje são 113 estações públicas para 1.522 km²: só 4% das células de ~460 m têm um pluviômetro.
              Os pontos amarelos são os pluviômetros reais desta área (CEMADEN e INMET na posição exata; CGE aproximada
              pelo bairro, que ela não publica). Cada sensor estima a chuva até 1,5 km ao redor.
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
      </main>
    </div>
  )
}
