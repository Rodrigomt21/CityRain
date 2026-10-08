import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ImageOff, ExternalLink } from 'lucide-react'
import { ResponsiveContainer, ScatterChart, Scatter, Cell, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import Topbar from '../components/layout/Topbar'
import { useCameras } from '../hooks/useCameras'
import { useSerieCamera } from '../hooks/useSerieCamera'
import { resumoCamera, pontosSerie, separarMedidos, rotuloTempo, ROTULOS_NIVEL } from '../lib/cameras'
import { BASE_URL } from '../api/client'

const JANELAS = [3, 6, 24]
const TICK = { fill: 'var(--text-secondary)', fontSize: 10, fontFamily: 'JetBrains Mono' }

function PontoTooltip({ active, payload, horas }) {
  const p = active && payload?.[0]?.payload
  if (!p) return null
  return (
    <div className="font-mono text-xs px-2 py-1 rounded"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)', color: 'var(--text-primary)' }}>
      {rotuloTempo(p.t, horas)} · {p.rotulo}
    </div>
  )
}

export default function CameraDetalhe() {
  const { id } = useParams()
  const [horas, setHoras] = useState(6)
  const [falhou, setFalhou] = useState(null)
  const { cameras, carregando: carregandoCams, error: erroCams } = useCameras()
  const { serie, agora, error, carregando } = useSerieCamera(id, horas)

  const cam = cameras.find(c => String(c.id) === String(id))
  const r = useMemo(() => (cam ? resumoCamera(cam, BASE_URL) : null), [cam])
  const { medidos, semMedida } = useMemo(() => separarMedidos(pontosSerie(serie)), [serie])
  const semImagem = r && falhou === r.imagemSrc

  const naoEncontrada = !cam && !carregandoCams && !erroCams

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb={r ? r.nome : 'Câmera fixa'} backTo="/cameras" />
      <main className="p-6 flex flex-col gap-4">
        {erroCams && <p className="font-mono text-xs" style={{ color: 'var(--cat-heavy)' }}>Não consegui falar com a API ({erroCams.message}).</p>}
        {!cam && carregandoCams && <p className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Carregando…</p>}
        {naoEncontrada && <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Câmera não encontrada.</p>}

        {r && (
          <>
            <section className="rounded-xl overflow-hidden flex flex-wrap"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)' }}>
              <div style={{ flex: '1 1 320px', maxWidth: 520, aspectRatio: '4 / 3', background: 'var(--bg-base)' }}>
                {r.imagemSrc && !semImagem ? (
                  <img src={r.imagemSrc} alt="" onError={() => setFalhou(r.imagemSrc)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <div className="flex flex-col items-center justify-center gap-1" style={{ height: '100%', color: 'var(--text-secondary)' }}>
                    <ImageOff size={24} />
                    <span className="font-mono text-xs">{r.imagemSrc ? 'imagem indisponível' : 'sem captura ainda'}</span>
                  </div>
                )}
              </div>
              <div className="p-4 flex flex-col gap-2" style={{ flex: '1 1 260px' }}>
                <h1 className="text-lg" style={{ color: 'var(--text-primary)', margin: 0 }}>{r.nome}</h1>
                {r.descricao && r.descricao !== r.nome && (
                  <p className="text-sm" style={{ color: 'var(--text-secondary)', margin: 0 }}>{r.descricao}</p>
                )}
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs px-2 py-1 rounded" style={{ background: r.categoria.color, color: '#0b1220' }}>
                    {r.categoria.label}
                  </span>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {r.quando}{r.confiancaPct != null && ` · confiança ${r.confiancaPct}%`}{r.aoVivo && ' · ao vivo'}
                  </span>
                </div>
                {/^https?:\/\//.test(cam.stream_url ?? '') && (
                  <a href={cam.stream_url} target="_blank" rel="noopener" className="flex items-center gap-1 text-sm"
                    style={{ color: 'var(--text-primary)', textDecoration: 'underline' }}>
                    abrir transmissão <ExternalLink size={14} />
                  </a>
                )}
              </div>
            </section>

            <section className="rounded-xl p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}>
              <div className="flex items-baseline justify-between mb-2" style={{ gap: 12, flexWrap: 'wrap' }}>
                <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1 }}>
                  CLASSE PREVISTA PELO MODELO
                </span>
                <div className="flex" style={{ gap: 6 }}>
                  {JANELAS.map(h => (
                    <button key={h} type="button" onClick={() => setHoras(h)} aria-pressed={h === horas}
                      className="font-mono text-xs px-2 py-1 rounded"
                      style={{
                        background: h === horas ? 'var(--bg-border)' : 'transparent',
                        color: h === horas ? 'var(--text-primary)' : 'var(--text-secondary)',
                        border: '1px solid var(--bg-border)', cursor: 'pointer',
                      }}>
                      {h} h
                    </button>
                  ))}
                </div>
              </div>

              {error && <p className="font-mono text-xs" style={{ color: 'var(--cat-heavy)' }}>Não consegui carregar a série ({error.message}).</p>}
              {carregando ? (
                <p className="text-xs" style={{ color: 'var(--text-secondary)', height: 220, display: 'grid', placeItems: 'center', margin: 0 }}>Carregando…</p>
              ) : medidos.length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--text-secondary)', height: 220, display: 'grid', placeItems: 'center', margin: 0 }}>
                  Sem capturas medidas nas últimas {horas} h.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <ScatterChart margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke="var(--bg-border)" vertical={false} />
                    <XAxis type="number" dataKey="t" scale="time" domain={[agora - horas * 3600e3, agora]} tickFormatter={t => rotuloTempo(t, horas)}
                      tick={TICK} axisLine={false} tickLine={false} minTickGap={32} />
                    <YAxis type="number" dataKey="nivel" domain={[-0.5, 3.5]} ticks={[0, 1, 2, 3]} interval={0}
                      tickFormatter={v => ROTULOS_NIVEL[v] ?? ''} tick={TICK} axisLine={false} tickLine={false} width={64} />
                    <Tooltip content={<PontoTooltip horas={horas} />} cursor={{ stroke: 'var(--bg-border)' }} />
                    <Scatter data={medidos} isAnimationActive={false}>
                      {medidos.map((p, i) => <Cell key={i} fill={p.cor} />)}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              )}
              {semMedida > 0 && (
                <p className="font-mono text-xs" style={{ color: 'var(--text-secondary)', margin: '8px 0 0' }}>
                  {semMedida} {semMedida === 1 ? 'captura sem medida' : 'capturas sem medida'} (não aparecem no gráfico)
                </p>
              )}
            </section>

            <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: 0 }}>
              Previsão do modelo fixo{r.modelo ? ` (${r.modelo})` : ''}. A leitura do pluviômetro aparece aqui quando a integração das estações estiver ativa.
            </p>
          </>
        )}
      </main>
    </div>
  )
}
