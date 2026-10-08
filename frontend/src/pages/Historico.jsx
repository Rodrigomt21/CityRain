import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapContainer, TileLayer, Polygon, Tooltip, useMap } from 'react-leaflet'
import { cellToBoundary } from 'h3-js'
import 'leaflet/dist/leaflet.css'
import Topbar from '../components/layout/Topbar'
import SerieTemporal from '../components/dashboard/SerieTemporal'
import { CATEGORIES, UNMEASURED, categoryFromLabel, SEVERITY_ORDER } from '../lib/categories'
import { useHistorico, PERIODOS } from '../hooks/useHistorico'

const CENTRO_SP = [-23.56, -46.62]
const ORDEM = [...SEVERITY_ORDER.slice().reverse(), 'unmeasured'] // seco, garoa, moderada, forte, não medido

// Classe predominante da célula (a de mais capturas; empate -> a mais severa)
function predominante(labels) {
  let melhor = null
  for (const [label, n] of Object.entries(labels)) {
    const cat = categoryFromLabel(label === 'unknown' ? null : label)
    const sev = SEVERITY_ORDER.indexOf(cat.key)
    if (!melhor || n > melhor.n || (n === melhor.n && sev !== -1 && sev < melhor.sev)) melhor = { cat, n, sev }
  }
  return melhor?.cat ?? UNMEASURED
}

function contarPorClasse(celulas) {
  const tot = Object.fromEntries(ORDEM.map(k => [k, 0]))
  for (const c of celulas) {
    for (const [label, n] of Object.entries(c.labels)) {
      tot[categoryFromLabel(label === 'unknown' ? null : label).key] += n
    }
  }
  return tot
}

// O Leaflet guarda o tamanho do container em cache e não percebe sozinho quando
// ele muda. Sem avisar, arrastar a alça do gráfico deixa faixa cinza e tiles
// desalinhados no mapa até o próximo zoom.
function AvisarRedimensionamento({ altura }) {
  const map = useMap()
  useEffect(() => { map.invalidateSize({ animate: false }) }, [map, altura])
  return null
}

// Enquadra o mapa nas células com dado sempre que elas mudam
function Enquadrar({ poligonos }) {
  const map = useMap()
  useEffect(() => {
    const pts = poligonos.flatMap(p => p.contorno)
    if (pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 15 })
  }, [map, poligonos])
  return null
}

const TIPOS = [
  { label: 'Todas', valor: null },
  { label: 'Fixas', valor: 'fixa' },
  { label: 'Móveis', valor: 'movel' },
]

const corDe = key => (CATEGORIES[key] ?? UNMEASURED).color
const nomeDe = key => (CATEGORIES[key] ?? UNMEASURED).label

// Altura do gráfico: arrastável pela alça. O teto é relativo à janela para a
// alça nunca empurrar o mapa para fora da tela em monitor pequeno.
const ALTURA_PADRAO = 150
const ALTURA_MIN = 80
const CHAVE_ALTURA = 'cityrain:altura-serie'
const limitar = h => Math.max(ALTURA_MIN, Math.min(h, Math.round(window.innerHeight * 0.55)))

function alturaSalva() {
  // localStorage lança em aba anônima / cookies bloqueados: o gráfico não pode
  // deixar de renderizar por causa de uma preferência de tamanho.
  try {
    const h = Number(localStorage.getItem(CHAVE_ALTURA))
    return h ? limitar(h) : ALTURA_PADRAO
  } catch {
    return ALTURA_PADRAO
  }
}

export default function Historico() {
  const [periodo, setPeriodo] = useState(PERIODOS[3])
  const [resolucao, setResolucao] = useState(8)
  const [incluirDemo, setIncluirDemo] = useState(false)
  const [tipo, setTipo] = useState(null)
  const [alturaSerie, setAlturaSerie] = useState(alturaSalva)
  const { celulas, capturas, loading, error } = useHistorico(periodo, resolucao, incluirDemo, tipo)

  // Arrastar a alça para cima aumenta o gráfico (e encolhe o mapa), para baixo diminui.
  function arrastar(e) {
    e.preventDefault()
    const yInicial = e.clientY
    const alturaInicial = alturaSerie
    const mover = ev => setAlturaSerie(limitar(alturaInicial + (yInicial - ev.clientY)))
    const soltar = ev => {
      window.removeEventListener('pointermove', mover)
      window.removeEventListener('pointerup', soltar)
      try {
        localStorage.setItem(CHAVE_ALTURA, String(limitar(alturaInicial + (yInicial - ev.clientY))))
      } catch { /* preferência é opcional */ }
    }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', soltar)
  }

  // Setas redimensionam sem mouse; a alça é focável por teclado.
  function teclado(e) {
    const passo = e.shiftKey ? 40 : 10
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    e.preventDefault()
    setAlturaSerie(h => {
      const nova = limitar(h + (e.key === 'ArrowUp' ? passo : -passo))
      try { localStorage.setItem(CHAVE_ALTURA, String(nova)) } catch { /* opcional */ }
      return nova
    })
  }

  const poligonos = useMemo(() => celulas.map(c => ({ ...c, cat: predominante(c.labels), contorno: cellToBoundary(c.cell) })), [celulas])
  const totais = useMemo(() => contarPorClasse(celulas), [celulas])
  const total = Object.values(totais).reduce((a, b) => a + b, 0)
  const maxN = Math.max(1, ...celulas.map(c => c.count))

  return (
    <div style={{ height: '100vh', background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
      <Topbar breadcrumb="Histórico" backTo="/dashboard" />
      <main style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '16px 20px', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <h1 className="font-mono font-bold" style={{ fontSize: 22, color: 'var(--text-primary)', margin: 0 }}>Histórico de capturas</h1>
            <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Células H3 coloridas pela classe predominante · intensidade estimada pelo modelo no backend
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {PERIODOS.map(p => (
              <button key={p.key} onClick={() => setPeriodo(p)} className="font-mono text-xs px-3 py-1.5 rounded"
                style={{ cursor: 'pointer', color: p.key === periodo.key ? 'var(--bg-base)' : 'var(--text-secondary)',
                  background: p.key === periodo.key ? 'var(--accent-brand)' : 'transparent', border: '1px solid var(--bg-border)' }}>
                {p.label}
              </button>
            ))}
            {TIPOS.map(t => (
              <button key={t.label} onClick={() => setTipo(t.valor)} className="font-mono text-xs px-3 py-1.5 rounded"
                style={{ cursor: 'pointer', color: t.valor === tipo ? 'var(--bg-base)' : 'var(--text-secondary)',
                  background: t.valor === tipo ? 'var(--accent-brand)' : 'transparent', border: '1px solid var(--bg-border)' }}>
                {t.label}
              </button>
            ))}
            <select value={resolucao} onChange={e => setResolucao(Number(e.target.value))} className="font-mono text-xs px-2 py-1.5 rounded"
              style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--bg-border)' }}>
              <option value={7}>H3 res 7 (~5 km²)</option>
              <option value={8}>H3 res 8 (~0,7 km²)</option>
              <option value={9}>H3 res 9 (~0,1 km²)</option>
            </select>
            <label className="font-mono text-xs" style={{ color: 'var(--text-secondary)', display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
              <input type="checkbox" checked={incluirDemo} onChange={e => setIncluirDemo(e.target.checked)} />
              incluir demonstração
            </label>
            <Link to="/dashboard" className="font-mono text-xs px-3 py-1.5 rounded no-underline"
              style={{ color: 'var(--accent-brand)', border: '1px solid #3b82f633' }}>← Ao vivo</Link>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>
          <aside className="rounded-xl p-4" style={{ width: 340, flexShrink: 0, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', overflowY: 'auto' }}>
            <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1, margin: 0 }}>CAPTURAS NO PERÍODO</p>
            <p className="font-mono font-bold" style={{ fontSize: 34, color: 'var(--text-primary)', margin: '4px 0 12px' }}>
              {loading ? '…' : total}
              <span className="text-xs" style={{ color: 'var(--text-secondary)', fontWeight: 400 }}> em {celulas.length} células</span>
            </p>
            {error && <p className="text-xs" style={{ color: '#ef4444' }}>API indisponível: {error.message}</p>}
            {ORDEM.map(k => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: corDe(k) }} />
                <span className="text-xs" style={{ color: 'var(--text-secondary)', flex: 1 }}>{nomeDe(k)}</span>
                <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{totais[k]}</span>
                <div style={{ width: 90, height: 6, background: 'var(--bg-border)', borderRadius: 3 }}>
                  <div style={{ width: `${total ? (100 * totais[k]) / total : 0}%`, height: '100%', background: corDe(k), borderRadius: 3 }} />
                </div>
              </div>
            ))}
            <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1, margin: '18px 0 6px' }}>ÚLTIMAS CAPTURAS</p>
            {capturas.slice(0, 25).map(c => {
              const cat = categoryFromLabel(c.weather_label)
              return (
                <div key={c.id} className="text-xs" style={{ display: 'flex', gap: 8, padding: '5px 0', borderTop: '1px solid var(--bg-border)' }}>
                  <span style={{ width: 8, height: 8, marginTop: 4, borderRadius: 4, background: cat.color, flexShrink: 0 }} />
                  <span className="font-mono" style={{ color: 'var(--text-secondary)', width: 118 }}>
                    {new Date(c.captured_at).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span style={{ color: cat.color, flex: 1 }}>{cat.label}</span>
                  <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{c.confidence != null ? `${Math.round(c.confidence * 100)}%` : '—'}</span>
                </div>
              )
            })}
          </aside>

          <div className="rounded-xl" style={{ flex: 1, minWidth: 0, overflow: 'hidden', border: '1px solid var(--bg-border)' }}>
            <MapContainer center={CENTRO_SP} zoom={12} style={{ height: '100%', width: '100%', background: '#0b1220' }}>
              <TileLayer
                className="mapa-escuro"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <Enquadrar poligonos={poligonos} />
              <AvisarRedimensionamento altura={alturaSerie} />
              {poligonos.map(p => (
                <Polygon key={p.cell} positions={p.contorno}
                  pathOptions={{ color: p.cat.color, weight: 1, fillColor: p.cat.color, fillOpacity: 0.25 + 0.55 * (p.count / maxN) }}>
                  <Tooltip sticky>
                    <div style={{ fontSize: 12 }}>
                      <b>{p.cat.label}</b> · {p.count} captura(s)<br />
                      {Object.entries(p.labels).map(([l, n]) => `${categoryFromLabel(l === 'unknown' ? null : l).label}: ${n}`).join(' · ')}
                    </div>
                  </Tooltip>
                </Polygon>
              ))}
            </MapContainer>
          </div>
        </div>

        <div style={{ flexShrink: 0 }}>
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Redimensionar o gráfico (setas para cima e para baixo)"
            aria-valuenow={alturaSerie}
            tabIndex={0}
            onPointerDown={arrastar}
            onKeyDown={teclado}
            title="Arraste para redimensionar o gráfico"
            style={{
              height: 14, cursor: 'ns-resize', display: 'grid', placeItems: 'center',
              touchAction: 'none', // sem isso o navegador rola a página em vez de arrastar
            }}
          >
            <span style={{ width: 46, height: 3, borderRadius: 2, background: 'var(--bg-border)' }} />
          </div>
          <SerieTemporal capturas={capturas} loading={loading} altura={alturaSerie} />
        </div>
      </main>
    </div>
  )
}
