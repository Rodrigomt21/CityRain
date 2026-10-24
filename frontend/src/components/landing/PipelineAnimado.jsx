import { useEffect, useMemo, useRef, useState } from 'react'
import { cellToBoundary, cellToLatLng, gridDisk, latLngToCell } from 'h3-js'
import { Car, Check, Server, X } from 'lucide-react'
import { CATEGORIES } from '../../lib/categories'
import './pipeline.css'

// "Vídeo" do pipeline: uma foto real percorre o caminho de produção até virar um hexágono H3.
// Dados reais: frame de 13/09/2026 16:51:31 (cityrain_frames3/frame_20260913_165131_962.jpg, placas borradas),
// GPS do manifesto, saída do modelo de produção (v14f) rodada nesta foto e leitura das estações (1,2 mm/h).
// O que é desenho (gotas, limpador, rede neural, placa) só ilustra a etapa; números e lugar são os medidos.
const FOTO = {
  src: '/pipeline/foto-1309.jpg',
  data: '13/09/2026', hora: '16:51:31',
  lat: -23.551238, lng: -46.594349,
  probs: [['drizzle', 0.856], ['moderate', 0.073], ['heavy', 0.071]],
  estacaoMm: '1,2',
}
const RES_H3 = 8
const PASSO_MS = 4200

const ETAPAS = [
  { titulo: 'A câmera fotografa', texto: 'A câmera no para-brisa tira uma foto, com GPS e horário.' },
  { titulo: 'A Jetson decide', texto: 'Ainda dentro do carro, a Jetson Nano vê se há chuva no vidro. Foto seca é descartada ali mesmo.' },
  { titulo: 'Vai para o servidor', texto: 'A foto com chuva sobe pela internet do celular, junto com o lugar e a hora.' },
  { titulo: 'O modelo estima', texto: 'Uma rede neural (MobileNetV3) olha a imagem e diz quanto está chovendo.' },
  { titulo: 'Vira um hexágono', texto: 'A posição cai numa célula H3 de ~460 m, pintada com a classe da chuva.' },
]

const GAROA = CATEGORIES.drizzle
const pct = v => `${Math.round(v * 100)}%`
const coord = v => v.toFixed(4).replace('.', ',')

// gotas no vidro: posições fixas (pseudoaleatórias) para a cena ser igual a cada volta
const GOTAS = Array.from({ length: 34 }, (_, i) => {
  const r = n => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1
  return { x: r(1) * 100, y: r(2) * 82, s: 0.5 + r(3) * 1.3, escorre: i % 4 === 0, atraso: r(4) * 2.4 }
})

// ---- mapa: Web Mercator para alinhar os tiles do OSM com os hexágonos ----
const Z = 15
const VB = { w: 800, h: 550 }
function mundo(lat, lng) {
  const n = 256 * 2 ** Z
  const s = Math.sin((lat * Math.PI) / 180)
  return [((lng + 180) / 360) * n, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n]
}
function useMapa() {
  return useMemo(() => {
    // enquadra o hexágono da foto um pouco à esquerda: o cartão da classe fica no canto direito
    const centro = latLngToCell(FOTO.lat, FOTO.lng, RES_H3)
    const [cx, cy] = mundo(...cellToLatLng(centro))
    const ox = cx - VB.w * 0.4
    const oy = cy - VB.h * 0.47
    const p = (la, ln) => { const [x, y] = mundo(la, ln); return [x - ox, y - oy] }
    const tiles = []
    for (let tx = Math.floor(ox / 256); tx <= Math.floor((ox + VB.w) / 256); tx++) {
      for (let ty = Math.floor(oy / 256); ty <= Math.floor((oy + VB.h) / 256); ty++) {
        tiles.push({ chave: `${tx}-${ty}`, x: tx * 256 - ox, y: ty * 256 - oy, src: `https://tile.openstreetmap.org/${Z}/${tx}/${ty}.png` })
      }
    }
    const hex = gridDisk(centro, 2).map(h => ({
      h, centro: h === centro,
      pontos: cellToBoundary(h).map(([la, ln]) => p(la, ln).map(n => n.toFixed(1)).join(',')).join(' '),
    }))
    return { tiles, hex, ponto: p(FOTO.lat, FOTO.lng), centro }
  }, [])
}

// ---- rede neural ilustrativa: colunas de nós, a última são as 3 classes ----
const CAMADAS = [5, 7, 7, 5, 3]
function useRede() {
  return useMemo(() => {
    const x0 = 40
    const x1 = 300
    const nos = CAMADAS.map((n, c) => Array.from({ length: n }, (_, i) => ({
      x: x0 + ((x1 - x0) * c) / (CAMADAS.length - 1), y: 125 + (i - (n - 1) / 2) * (c === CAMADAS.length - 1 ? 56 : 30),
    })))
    const arestas = []
    for (let c = 0; c < nos.length - 1; c++) {
      nos[c].forEach((a, i) => nos[c + 1].forEach((b, j) => arestas.push({ chave: `${c}-${i}-${j}`, c, a, b })))
    }
    return { nos, arestas }
  }, [])
}

function CenaCamera() {
  return (
    <div className="pl-cena pl-c0">
      <img className="pl-foto-cheia" src={FOTO.src} alt="Foto real da câmera do carro com garoa, 13/09/2026, Mooca" width={640} height={440} />
      <div className="pl-gotas" aria-hidden>
        {GOTAS.map((g, i) => (
          <span key={i} className={g.escorre ? 'pl-gota pl-gota-escorre' : 'pl-gota'}
            style={{ left: `${g.x}%`, top: `${g.y}%`, '--s': g.s, animationDelay: `${g.atraso}s` }} />
        ))}
      </div>
      <div className="pl-limpador" aria-hidden />
      <div className="pl-visor" aria-hidden><i /><i /><i /><i /></div>
      <div className="pl-rec font-mono"><span />REC</div>
      <div className="pl-flash" />
      <div className="pl-hud font-mono">
        <span>{FOTO.data} · {FOTO.hora}</span>
        <span>GPS {coord(FOTO.lat)}, {coord(FOTO.lng)}</span>
      </div>
    </div>
  )
}

function PlacaJetson() {
  return (
    <svg viewBox="0 0 220 150" className="pl-placa" aria-hidden>
      <defs>
        <linearGradient id="pl-dissip" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#3a4352" /><stop offset="1" stopColor="#1c222c" /></linearGradient>
      </defs>
      <rect x="4" y="18" width="212" height="128" rx="8" fill="#0f2a1e" stroke="#1f5a3e" strokeWidth="2" />
      {Array.from({ length: 20 }, (_, i) => <rect key={i} x={14 + i * 9.6} y="6" width="5" height="14" rx="1" fill="#c9a227" />)}
      <rect x="40" y="34" width="120" height="90" rx="6" fill="url(#pl-dissip)" />
      {Array.from({ length: 11 }, (_, i) => <rect key={i} x={46 + i * 10.4} y="38" width="5" height="82" rx="2" fill="#4b5566" />)}
      <rect x="172" y="40" width="34" height="22" rx="3" fill="#2b3240" />
      <rect x="172" y="70" width="34" height="22" rx="3" fill="#2b3240" />
      <circle cx="190" cy="118" r="5" className="pl-led" />
      <text x="110" y="141" textAnchor="middle" className="pl-placa-nome">JETSON NANO · NO CARRO</text>
    </svg>
  )
}

function CenaJetson() {
  return (
    <div className="pl-cena pl-c1">
      <div className="pl-j-foto">
        <img src={FOTO.src} alt="" width={640} height={440} />
        <div className="pl-scan" />
      </div>
      <div className="pl-feixe" aria-hidden><span /><span /><span /></div>
      <div className="pl-j-placa">
        <PlacaJetson />
        <div className="pl-veredito font-mono"><Check size="1.1em" strokeWidth={3} /> chuva no vidro → envia</div>
      </div>
      <div className="pl-descarte font-mono">
        <div className="pl-seca"><X size="1.4em" /></div>
        foto seca: descartada no carro
      </div>
    </div>
  )
}

function CenaEnvio() {
  return (
    <div className="pl-cena pl-c2">
      <svg viewBox="0 0 400 275" className="pl-arco-svg" aria-hidden>
        <path d="M 70 190 Q 200 20 330 190" className="pl-arco" />
        <path d="M 70 190 Q 200 20 330 190" className="pl-arco-luz" />
      </svg>
      <div className="pl-no pl-no-carro">
        <span className="pl-ondas"><i /><i /><i /></span>
        <Car size="2.2em" strokeWidth={1.6} />
        <span className="font-mono">carro</span>
      </div>
      <div className="pl-no pl-no-servidor">
        <Server size="2.2em" strokeWidth={1.6} />
        <span className="font-mono">servidor</span>
      </div>
      <div className="pl-pacote"><img src={FOTO.src} alt="" width={640} height={440} /></div>
      <pre className="pl-json font-mono">{`POST /api/v1/ingest
{ "lat": ${FOTO.lat.toFixed(4)},
  "lon": ${FOTO.lng.toFixed(4)},
  "hora": "${FOTO.hora}",
  "imagem": "foto.jpg" }`}</pre>
    </div>
  )
}

function CenaModelo() {
  const { nos, arestas } = useRede()
  const saida = nos[nos.length - 1]
  return (
    <div className="pl-cena pl-c3">
      <img className="pl-m-foto" src={FOTO.src} alt="" width={640} height={440} />
      <svg viewBox="0 0 400 250" className="pl-rede" aria-hidden>
        {arestas.map(e => (
          <line key={e.chave} x1={e.a.x} y1={e.a.y} x2={e.b.x} y2={e.b.y} className="pl-aresta" style={{ animationDelay: `${0.35 + e.c * 0.32}s` }} />
        ))}
        {nos.map((col, c) => col.map((n, i) => {
          const fim = c === nos.length - 1
          const k = fim ? FOTO.probs[i][0] : null
          return (
            <circle key={`${c}-${i}`} cx={n.x} cy={n.y} r={fim ? 9 : 5.5}
              className={fim ? (i === 0 ? 'pl-no-rede pl-no-vence' : 'pl-no-rede pl-no-saida') : 'pl-no-rede'}
              style={{ animationDelay: `${0.3 + c * 0.32}s`, ...(fim ? { '--cor': CATEGORIES[k].color } : {}) }} />
          )
        }))}
        {saida.map((n, i) => (
          <text key={i} x={n.x + 18} y={n.y + 4} className="pl-saida-txt" style={{ fill: CATEGORIES[FOTO.probs[i][0]].color }}>
            {CATEGORIES[FOTO.probs[i][0]].label} {pct(FOTO.probs[i][1])}
          </text>
        ))}
      </svg>
      <div className="pl-m-resultado">
        <span className="font-mono pl-m-rotulo">MOBILENETV3 · SAÍDA DO MODELO</span>
        <span className="pl-m-classe" style={{ color: GAROA.color }}>{GAROA.label}</span>
        <span className="font-mono pl-m-conf">{pct(FOTO.probs[0][1])} de confiança</span>
      </div>
    </div>
  )
}

function CenaMapa() {
  const { tiles, hex, ponto, centro } = useMapa()
  return (
    <div className="pl-cena pl-c4">
      <svg viewBox={`0 0 ${VB.w} ${VB.h}`} preserveAspectRatio="xMidYMid slice" className="pl-mapa-svg" role="img"
        aria-label="Mapa da Mooca com a célula H3 da foto pintada como garoa">
        <defs>
          {/* tema escuro dos tiles: inverte, gira o matiz de volta, tira saturação e escurece */}
          <filter id="pl-escuro" colorInterpolationFilters="sRGB">
            <feColorMatrix type="matrix" values="-1 0 0 0 1  0 -1 0 0 1  0 0 -1 0 1  0 0 0 1 0" />
            <feColorMatrix type="hueRotate" values="180" />
            <feColorMatrix type="saturate" values="0.35" />
            <feComponentTransfer>
              <feFuncR type="linear" slope="0.78" intercept="0.01" />
              <feFuncG type="linear" slope="0.8" intercept="0.02" />
              <feFuncB type="linear" slope="0.9" intercept="0.04" />
            </feComponentTransfer>
          </filter>
        </defs>
        <g className="pl-zoom" style={{ transformOrigin: `${ponto[0]}px ${ponto[1]}px` }}>
          <g className="pl-tiles">
            {tiles.map(t => <image key={t.chave} href={t.src} x={t.x} y={t.y} width="256" height="256" />)}
          </g>
          {hex.map((c, i) => (
            <polygon key={c.h} points={c.pontos} className={c.centro ? 'pl-hex pl-hex-centro' : 'pl-hex'}
              style={c.centro ? { '--cor': GAROA.color } : { animationDelay: `${0.3 + i * 0.05}s` }} />
          ))}
          <circle cx={ponto[0]} cy={ponto[1]} r="34" className="pl-onda" style={{ '--cor': GAROA.color, transformOrigin: `${ponto[0]}px ${ponto[1]}px` }} />
          <g className="pl-pino" style={{ transformOrigin: `${ponto[0]}px ${ponto[1]}px` }}>
            <path d={`M ${ponto[0]} ${ponto[1]} c -10 -14 -16 -22 -16 -31 a 16 16 0 1 1 32 0 c 0 9 -6 17 -16 31 z`} fill="#fff" />
            <circle cx={ponto[0]} cy={ponto[1] - 31} r="6" fill={GAROA.color} />
          </g>
        </g>
      </svg>
      <div className="pl-cartao font-mono">
        <span className="pl-cartao-classe" style={{ color: GAROA.color }}>■ {GAROA.label}</span>
        <span>célula H3 {centro} · Mooca</span>
        <span>estações da região: {FOTO.estacaoMm} mm/h</span>
      </div>
      <span className="pl-osm font-mono">© OpenStreetMap</span>
    </div>
  )
}

function Palco({ etapa, rodando }) {
  return (
    <div className="pl-palco" data-etapa={etapa}>
      <div className="pl-ambiente" aria-hidden />
      <CenaCamera />
      <CenaJetson />
      <CenaEnvio />
      <CenaModelo />
      <CenaMapa />
      <div className="pl-titulo font-mono" key={etapa}>
        <b>{etapa + 1}</b>{ETAPAS[etapa].titulo}
      </div>
      <div className="pl-trilha" aria-hidden>
        {ETAPAS.map((_, i) => (
          <span key={i} className={i < etapa ? 'pl-seg pl-seg-feito' : 'pl-seg'}>
            {i === etapa && <i key={`${etapa}-${rodando}`} className={rodando ? 'pl-seg-anda' : 'pl-seg-cheio'} style={{ animationDuration: `${PASSO_MS}ms` }} />}
          </span>
        ))}
      </div>
    </div>
  )
}

/**
 * Palco + lista de etapas, com o próprio relógio. Roda só quando está na tela.
 * `grande`: versão do telão (letras maiores). `retomarMs`: depois de um clique numa etapa, volta a andar
 * sozinho após esse tempo. `manual`: só troca de etapa com clique ou teclado (→/espaço/PageDown avança,
 * ←/PageUp volta), para quem apresenta no telão controlar o ritmo.
 */
export function Pipeline({ grande = false, retomarMs = null, manual = false }) {
  const [etapa, setEtapa] = useState(0)
  const [visivel, setVisivel] = useState(false)
  const [pausado, setPausado] = useState(false)
  const ref = useRef(null)
  const reduzido = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  // começa quando entra na tela ("ao descer") e para quando sai
  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) { setVisivel(true); return undefined }
    const obs = new IntersectionObserver(([e]) => setVisivel(e.isIntersecting), { threshold: 0.35 })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const rodando = visivel && !pausado && !reduzido && !manual
  useEffect(() => {
    if (!rodando) return undefined
    const id = setTimeout(() => setEtapa(e => (e + 1) % ETAPAS.length), PASSO_MS)
    return () => clearTimeout(id)
  }, [rodando, etapa])

  useEffect(() => {
    if (!pausado || retomarMs == null) return undefined
    const id = setTimeout(() => setPausado(false), retomarMs)
    return () => clearTimeout(id)
  }, [pausado, retomarMs, etapa])

  useEffect(() => {
    if (!manual) return undefined
    const tecla = ev => {
      const passo = { ArrowRight: 1, ' ': 1, PageDown: 1, ArrowLeft: -1, PageUp: -1 }[ev.key]
      if (!passo) return
      ev.preventDefault()
      setEtapa(e => (e + passo + ETAPAS.length) % ETAPAS.length)
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [manual])

  const escolher = i => { setEtapa(i); setPausado(true) }
  const fonte = grande ? { titulo: 'clamp(16px, 1.5vw, 26px)', texto: 'clamp(14px, 1.2vw, 21px)', num: 'clamp(13px, 1.1vw, 18px)' }
    : { titulo: 14, texto: 14, num: 12 }

  return (
    <div ref={ref} className={`grid gap-6 md:items-center ${grande ? 'md:grid-cols-[2.2fr_1fr] pl-grande' : 'md:grid-cols-[1.6fr_1fr]'}`}>
      <Palco etapa={etapa} rodando={rodando} />

      <ol className="flex flex-col gap-1" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {ETAPAS.map((e, i) => {
          const ativa = i === etapa
          return (
            <li key={e.titulo}>
              <button type="button" onClick={() => escolher(i)} aria-current={ativa ? 'step' : undefined}
                className="w-full text-left rounded-lg px-4 py-3"
                style={{ background: ativa ? 'var(--bg-card)' : 'transparent', border: `1px solid ${ativa ? 'var(--bg-border)' : 'transparent'}`, cursor: 'pointer', color: 'inherit' }}>
                <span className="flex items-center gap-3">
                  <span className="font-mono" style={{ fontSize: fonte.num, color: ativa ? 'var(--accent-brand)' : 'var(--text-secondary)' }}>{i + 1}</span>
                  <span className="font-mono font-semibold" style={{ fontSize: fonte.titulo, color: ativa ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{e.titulo}</span>
                </span>
                {ativa && (
                  <span className="block mt-1.5" style={{ fontSize: fonte.texto, color: 'var(--text-secondary)', lineHeight: 1.5, paddingLeft: 22 }}>{e.texto}</span>
                )}
              </button>
            </li>
          )
        })}
        {pausado && !reduzido && !manual && retomarMs == null && (
          <li>
            <button type="button" onClick={() => setPausado(false)} className="font-mono text-xs px-4 py-2"
              style={{ background: 'none', border: 0, color: 'var(--accent-brand)', cursor: 'pointer' }}>
              ▶ continuar sozinho
            </button>
          </li>
        )}
      </ol>
    </div>
  )
}

/** Seção da landing: título + pipeline. */
export default function PipelineAnimado() {
  return (
    <section className="py-20 px-4 sm:px-6" style={{ background: 'var(--bg-base)', borderTop: '1px solid var(--bg-border)' }}>
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-10">
          <h2 className="font-mono font-bold" style={{ fontSize: '1.6rem', color: 'var(--text-primary)', margin: 0 }}>
            Do para-brisa ao mapa
          </h2>
          <p className="font-sans text-sm" style={{ color: 'var(--text-secondary)', maxWidth: 520, margin: '12px auto 0', lineHeight: 1.6 }}>
            O caminho de uma foto de verdade, tirada pelo nosso carro em 13/09, até virar um hexágono no mapa.
          </p>
        </div>
        <Pipeline />
      </div>
    </section>
  )
}
