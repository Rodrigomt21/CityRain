import { useEffect, useMemo, useRef, useState } from 'react'
import { cellToBoundary, gridDisk, latLngToCell } from 'h3-js'
import { CATEGORIES } from '../../lib/categories'

// "Vídeo" do pipeline: uma foto real percorre o caminho de produção até virar um hexágono H3.
// Dados reais: frame de 13/09/2026 16:51:31 (cityrain_frames3/frame_20260913_165131_962.jpg, placas borradas),
// GPS do manifesto, saída do modelo de produção (v14f) rodada nesta foto e leitura das estações (1,2 mm/h).
const FOTO = {
  src: '/pipeline/foto-1309.jpg',
  quando: '13/09/2026 · 16:51:31',
  lat: -23.551238, lng: -46.594349,
  probs: [['drizzle', 0.856], ['moderate', 0.073], ['heavy', 0.071]],
  estacaoMm: '1,2',
}
const RES_H3 = 8
const PASSO_MS = 3200

const ETAPAS = [
  { titulo: 'A câmera fotografa', texto: 'A câmera no para-brisa tira uma foto, com GPS e horário.' },
  { titulo: 'A Jetson decide', texto: 'Ainda dentro do carro, a Jetson Nano vê se há chuva no vidro. Foto seca é descartada ali mesmo.' },
  { titulo: 'Vai para o servidor', texto: 'A foto com chuva sobe pela internet do celular, junto com o lugar e a hora.' },
  { titulo: 'O modelo estima', texto: 'Uma rede neural (MobileNetV3) olha a imagem e diz quanto está chovendo.' },
  { titulo: 'Vira um hexágono', texto: 'A posição cai numa célula H3 de ~460 m, pintada com a classe da chuva.' },
]

const pct = v => `${Math.round(v * 100)}%`
const coord = v => v.toFixed(4).replace('.', ',')

/** Hexágonos H3 em volta da foto, projetados num viewBox 0..400 x 0..250. */
function useHexagonos() {
  return useMemo(() => {
    const centro = latLngToCell(FOTO.lat, FOTO.lng, RES_H3)
    const cos = Math.cos((FOTO.lat * Math.PI) / 180)
    const escala = 5200
    const proj = ([la, ln]) => [200 + (ln - FOTO.lng) * cos * escala, 125 - (la - FOTO.lat) * escala]
    const celulas = gridDisk(centro, 5).map(h => ({
      h, centro: h === centro, pontos: cellToBoundary(h).map(proj).map(p => p.map(n => n.toFixed(1)).join(',')).join(' '),
    }))
    return { celulas, ponto: proj([FOTO.lat, FOTO.lng]), centro }
  }, [])
}

function Palco({ etapa }) {
  const { celulas, ponto, centro } = useHexagonos()
  const garoa = CATEGORIES.drizzle
  return (
    <div className="pl-palco" data-etapa={etapa}>
      {/* 0-2: a foto */}
      <div className="pl-foto">
        <img src={FOTO.src} alt="Foto real da câmera do carro com garoa, 13/09/2026, Mooca" width={640} height={440} />
        <div className="pl-flash" />
        <div className="pl-scan" />
        <div className="pl-meta font-mono">{FOTO.quando} · {coord(FOTO.lat)}, {coord(FOTO.lng)}</div>
      </div>

      {/* 1: decisão da Jetson */}
      <div className="pl-jetson font-mono">
        <div className="pl-chip">JETSON NANO<br /><span>no carro</span></div>
        <div className="pl-veredito">chuva no vidro? <b>sim</b> → envia</div>
        <div className="pl-descarte">foto seca: descartada aqui</div>
      </div>

      {/* 2: envio */}
      <div className="pl-envio font-mono">
        <div className="pl-no">carro</div>
        <div className="pl-trilho"><div className="pl-pacote">foto + GPS + hora</div></div>
        <div className="pl-no">servidor</div>
        <div className="pl-rota">POST /api/v1/ingest</div>
      </div>

      {/* 3: modelo */}
      <div className="pl-modelo">
        <div className="font-mono pl-rotulo">MOBILENETV3 · SAÍDA DO MODELO</div>
        {FOTO.probs.map(([k, p], i) => (
          <div key={k} className="pl-barra-linha">
            <span className="font-mono" style={{ width: '6.2em', flexShrink: 0, color: CATEGORIES[k].color }}>{CATEGORIES[k].label}</span>
            <div className="pl-barra"><div style={{ width: pct(p), background: CATEGORIES[k].color, transitionDelay: `${0.25 + i * 0.15}s` }} /></div>
            <span className="font-mono" style={{ width: '3em', flexShrink: 0, textAlign: 'right' }}>{pct(p)}</span>
          </div>
        ))}
        <div className="pl-resultado font-mono" style={{ color: garoa.color }}>→ {garoa.label}</div>
      </div>

      {/* 4: H3 */}
      <div className="pl-mapa">
        <svg viewBox="0 0 400 250" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Célula H3 da foto pintada como garoa">
          {celulas.map((c, i) => (
            <polygon key={c.h} points={c.pontos} className={c.centro ? 'pl-hex pl-hex-centro' : 'pl-hex'}
              style={c.centro ? { fill: garoa.color, stroke: garoa.color } : { transitionDelay: `${(i % 9) * 0.04}s` }} />
          ))}
          <circle cx={ponto[0]} cy={ponto[1]} r="5" className="pl-pino" />
        </svg>
        <div className="pl-legenda-mapa font-mono">
          <span style={{ color: garoa.color }}>■ {garoa.label}</span> · célula H3 {centro.slice(0, 9)}… · Mooca
          <br />estações da região: {FOTO.estacaoMm} mm/h (garoa)
        </div>
      </div>
    </div>
  )
}

/**
 * Palco + lista de etapas, com o próprio relógio. Roda só quando está na tela.
 * `grande`: versão do telão (letras maiores). `retomarMs`: depois de um clique numa etapa, volta a andar
 * sozinho após esse tempo (no telão ninguém fica para apertar "continuar").
 */
export function Pipeline({ grande = false, retomarMs = null }) {
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

  const rodando = visivel && !pausado && !reduzido
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

  const escolher = i => { setEtapa(i); setPausado(true) }
  const fonte = grande ? { titulo: 'clamp(16px, 1.5vw, 26px)', texto: 'clamp(14px, 1.2vw, 21px)', num: 'clamp(13px, 1.1vw, 18px)' }
    : { titulo: 14, texto: 14, num: 12 }

  return (
    <div ref={ref} className={`grid gap-6 md:items-center ${grande ? 'md:grid-cols-[2.2fr_1fr] pl-grande' : 'md:grid-cols-[1.6fr_1fr]'}`}>
      <Palco etapa={etapa} />

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
                  <>
                    <span className="block mt-1.5" style={{ fontSize: fonte.texto, color: 'var(--text-secondary)', lineHeight: 1.5, paddingLeft: 22 }}>{e.texto}</span>
                    {rodando && <span className="pl-progresso" key={etapa} style={{ animationDuration: `${PASSO_MS}ms` }} />}
                  </>
                )}
              </button>
            </li>
          )
        })}
        {pausado && !reduzido && retomarMs == null && (
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
