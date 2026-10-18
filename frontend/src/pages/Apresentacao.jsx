import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Camera, Car, Cpu, Database, Monitor, Radio, Sparkles } from 'lucide-react'
import MapaAoVivo from '../components/dashboard/MapaAoVivo'
import { BASE_URL } from '../api/client'
import { useCameras } from '../hooks/useCameras'
import { useLiveCaptures, JANELA_MIN } from '../hooks/useLiveCaptures'
import { useMoveis } from '../hooks/useMoveis'
import { CATEGORIES, UNMEASURED, categoryFromLabel } from '../lib/categories'
import { resumoCamera } from '../lib/cameras'
import { celulasH3, dispositivosDoMapa, ehDemo } from '../lib/dispositivos'
import { camerasAoVivo, confiancaMedia, contagemPorClasse, feed, gotasPorClasse } from '../lib/apresentacao'

// Modo apresentação (defesa): tela cheia para projetor, só leitura, mesmas fontes do ao vivo.
// Carro: classe da última foto + trajeto; câmeras fixas: miniatura e classe; pipeline pisca a cada captura nova.

const ORDEM = ['dry', 'drizzle', 'moderate', 'heavy']

/** "Agora" que avança a cada segundo: relógio, frescor da foto do carro e veículos ativos. */
function useAgora() {
  const [agora, setAgora] = useState(() => new Date())
  useEffect(() => { const id = setInterval(() => setAgora(new Date()), 1000); return () => clearInterval(id) }, [])
  return agora
}

function Relogio({ agora }) {
  return (
    <span className="font-mono" style={{ fontSize: 22, color: 'var(--text-primary)', letterSpacing: 1 }}>
      {agora.toLocaleTimeString('pt-BR')}
    </span>
  )
}

/** Chuva animada por cima do card: quantidade de gotas pela classe (seco = céu limpo). */
function Chuva({ categoria }) {
  const n = gotasPorClasse(categoria)
  const gotas = useMemo(() => Array.from({ length: n }, (_, i) => ({
    left: (i * 37.3) % 100, atraso: ((i * 0.173) % 1.2).toFixed(2), dur: (0.55 + ((i * 0.071) % 0.5)).toFixed(2),
  })), [n])
  return (
    <div aria-hidden style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
      {gotas.map((g, i) => (
        <span key={i} className="ap-gota" style={{ left: `${g.left}%`, animationDelay: `${g.atraso}s`, animationDuration: `${g.dur}s` }} />
      ))}
    </div>
  )
}

function Kpi({ rotulo, valor, detalhe }) {
  return (
    <div style={{ flex: 1, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 12, padding: '12px 16px' }}>
      <div className="font-mono" style={{ fontSize: 11, letterSpacing: 1.5, color: 'var(--text-secondary)' }}>{rotulo}</div>
      <div className="font-mono font-bold" style={{ fontSize: 30, color: 'var(--text-primary)', lineHeight: 1.15 }}>{valor}</div>
      {detalhe && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{detalhe}</div>}
    </div>
  )
}

function CardCarro({ ultima, recentes, agora }) {
  const fresca = ultima && (agora.getTime() - new Date(ultima.captured_at).getTime()) / 60e3 <= 2
  const cat = fresca ? categoryFromLabel(ultima.weather_label) : UNMEASURED
  const conf = fresca && ultima.confidence != null ? Math.round(ultima.confidence * 100) : null
  const cont = contagemPorClasse(recentes)
  const total = Object.values(cont).reduce((a, b) => a + b, 0)
  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '18px 22px',
      background: `linear-gradient(135deg, ${cat.color}33, var(--bg-card) 60%)`, border: `1px solid ${cat.color}66`,
      transition: 'background 0.6s, border-color 0.6s' }}>
      {fresca && <Chuva categoria={cat} />}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="font-mono" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, letterSpacing: 1.5, color: 'var(--text-secondary)' }}>
          <Car size={16} /> CARRO · CÂMERA NO PARA-BRISA
        </span>
        {fresca && ehDemo(ultima) && (
          <span className="font-mono" style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, color: '#fbbf24', border: '1px solid #fbbf2466' }}>
            REPLAY 23/09
          </span>
        )}
      </div>
      <div key={ultima?.id} className="font-mono font-bold ap-entrar"
        style={{ position: 'relative', fontSize: 64, lineHeight: 1.1, color: cat.color, marginTop: 6, textShadow: `0 0 28px ${cat.color}55` }}>
        {fresca ? cat.label.toUpperCase() : 'AGUARDANDO'}
      </div>
      <div style={{ position: 'relative', fontSize: 14, color: 'var(--text-secondary)', minHeight: 20 }}>
        {fresca ? `confiança ${conf ?? '—'}% · ${new Date(ultima.captured_at).toLocaleTimeString('pt-BR')}` : 'sem foto do carro nos últimos 2 min'}
      </div>
      {conf != null && (
        <div style={{ position: 'relative', height: 6, borderRadius: 3, background: 'var(--bg-border)', marginTop: 10 }}>
          <div style={{ width: `${conf}%`, height: '100%', borderRadius: 3, background: cat.color, transition: 'width 0.6s' }} />
        </div>
      )}
      <div style={{ position: 'relative', display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', marginTop: 14, background: 'var(--bg-border)' }}>
        {total > 0 && ORDEM.map(k => cont[k] > 0 && (
          <div key={k} style={{ width: `${(100 * cont[k]) / total}%`, background: CATEGORIES[k].color, transition: 'width 0.6s' }} />
        ))}
      </div>
      <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
        {ORDEM.map(k => (
          <span key={k} className="font-mono" style={{ fontSize: 12, color: CATEGORIES[k].color }}>
            {CATEGORIES[k].label} {cont[k]}
          </span>
        ))}
      </div>
    </div>
  )
}

const ETAPAS = [
  { icone: Car, titulo: 'Jetson', texto: 'câmera + GPS' },
  { icone: Radio, titulo: 'API', texto: 'POST /ingest' },
  { icone: Cpu, titulo: 'Modelo', texto: 'MobileNetV3 · ONNX' },
  { icone: Database, titulo: 'PostgreSQL', texto: 'célula H3' },
  { icone: Monitor, titulo: 'Painel', texto: 'ao vivo' },
]

/** Pipeline de produção; `pulso` muda a cada captura nova e reinicia a onda de luz da esquerda para a direita. */
function Pipeline({ pulso }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 16, padding: '14px 16px' }}>
      <div className="font-mono" style={{ fontSize: 12, letterSpacing: 1.5, color: 'var(--text-secondary)', marginBottom: 10 }}>
        PIPELINE DE PRODUÇÃO · CADA FOTO PERCORRE
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {ETAPAS.map((e, i) => {
          const Icone = e.icone
          return (
            <div key={e.titulo} style={{ display: 'flex', alignItems: 'center', flex: i < ETAPAS.length - 1 ? 1 : 'none' }}>
              <div key={`${pulso}-${i}`} className="ap-etapa" style={{ animationDelay: `${i * 0.22}s`, textAlign: 'center', minWidth: 74 }}>
                <div style={{ width: 42, height: 42, margin: '0 auto', borderRadius: 12, display: 'grid', placeItems: 'center',
                  background: '#3b82f61a', border: '1px solid #3b82f655', color: 'var(--accent-brand)' }}>
                  <Icone size={20} />
                </div>
                <div className="font-mono" style={{ fontSize: 12, color: 'var(--text-primary)', marginTop: 6 }}>{e.titulo}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{e.texto}</div>
              </div>
              {i < ETAPAS.length - 1 && (
                <div style={{ flex: 1, height: 2, margin: '0 4px 30px', background: 'var(--bg-border)', position: 'relative', overflow: 'hidden' }}>
                  <span key={`${pulso}-l${i}`} className="ap-fluxo" style={{ animationDelay: `${i * 0.22 + 0.1}s` }} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Feed({ itens }) {
  return (
    <div style={{ flex: 1, minHeight: 0, background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 16, padding: '14px 16px', overflow: 'hidden' }}>
      <div className="font-mono" style={{ fontSize: 12, letterSpacing: 1.5, color: 'var(--text-secondary)', marginBottom: 8 }}>ÚLTIMAS CLASSIFICAÇÕES</div>
      {itens.length === 0 && <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Aguardando a primeira foto…</div>}
      {itens.map(it => (
        <div key={it.id} className="ap-entrar" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: '1px solid var(--bg-border)' }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: it.categoria.color, flexShrink: 0, boxShadow: `0 0 10px ${it.categoria.color}` }} />
          <span className="font-mono" style={{ fontSize: 13, color: 'var(--text-secondary)', width: 70 }}>{new Date(it.quando).toLocaleTimeString('pt-BR')}</span>
          <span style={{ fontSize: 14, color: 'var(--text-primary)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {it.origem}{it.demo ? ' · replay' : ''}
          </span>
          <span className="font-mono" style={{ fontSize: 13, color: it.categoria.color }}>{it.categoria.label}</span>
          <span className="font-mono" style={{ fontSize: 12, color: 'var(--text-secondary)', width: 38, textAlign: 'right' }}>
            {it.confiancaPct != null ? `${it.confiancaPct}%` : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function FaixaCameras({ cameras }) {
  const resumos = cameras.map(c => resumoCamera(c, BASE_URL)).slice(0, 6)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(resumos.length, 1)}, 1fr)`, gap: 10 }}>
      {resumos.length === 0 && (
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', padding: 12 }}>Nenhuma câmera fixa cadastrada nesta API.</div>
      )}
      {resumos.map(r => (
        <Link key={r.id} to={`/cameras/${r.id}`} className="no-underline"
          style={{ position: 'relative', borderRadius: 12, overflow: 'hidden', border: `2px solid ${r.aoVivo ? r.categoria.color : 'var(--bg-border)'}`,
            background: 'var(--bg-card)', aspectRatio: '16 / 9', display: 'block' }}>
          {r.imagemSrc
            ? <img src={r.imagemSrc} alt={`Última foto da câmera ${r.nome}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            : <div style={{ height: '100%', display: 'grid', placeItems: 'center', color: 'var(--text-secondary)' }}><Camera size={26} /></div>}
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 8px 6px', background: 'linear-gradient(transparent, #0a0d12ee)' }}>
            <div style={{ fontSize: 12, color: '#e8edf5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.nome}</div>
            <div className="font-mono" style={{ fontSize: 12, color: r.categoria.color }}>
              {r.categoria.label}{r.confiancaPct != null ? ` · ${r.confiancaPct}%` : ''} · <span style={{ color: '#8896aa' }}>{r.quando}</span>
            </div>
          </div>
          {r.aoVivo && <span className="ap-ponto-vivo" style={{ position: 'absolute', top: 8, right: 8 }} />}
        </Link>
      ))}
    </div>
  )
}

export default function Apresentacao() {
  const { recentes, ultima } = useLiveCaptures()
  const { cameras } = useCameras()
  const { moveis } = useMoveis()
  const celulas = useMemo(() => celulasH3(dispositivosDoMapa(cameras, moveis, BASE_URL)), [cameras, moveis])

  // pipeline pisca quando chega captura nova do carro ou de qualquer câmera
  const assinatura = `${ultima?.id ?? ''}|${cameras.map(c => c.ultima_captura?.id ?? '').join(',')}`
  const anterior = useRef(assinatura)
  const [pulso, setPulso] = useState(0)
  useEffect(() => {
    if (anterior.current !== assinatura) { anterior.current = assinatura; setPulso(p => p + 1) }
  }, [assinatura])

  const agora = useAgora()
  const veiculosAtivos = moveis.filter(m => m.captura && (agora.getTime() - new Date(m.captura.captured_at).getTime()) / 60e3 <= JANELA_MIN).length
  const conf = confiancaMedia(recentes)

  return (
    <div style={{ height: '100vh', background: 'radial-gradient(1200px 600px at 70% -10%, #1e3a8a33, transparent), var(--bg-base)',
      display: 'flex', flexDirection: 'column', padding: '18px 24px', gap: 14, overflow: 'hidden' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <Link to="/dashboard" className="no-underline" style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span className="font-mono font-bold" style={{ fontSize: 28, color: 'var(--text-primary)' }}>City<span style={{ color: 'var(--accent-brand)' }}>Rain</span></span>
          <span style={{ fontSize: 15, color: 'var(--text-secondary)' }}>intensidade de chuva estimada por câmeras, em tempo real</span>
        </Link>
        <div style={{ flex: 1 }} />
        <Link to="/simulacao" className="font-mono no-underline" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
          padding: '8px 14px', borderRadius: 999, color: '#e9d5ff', background: 'linear-gradient(90deg, #7c3aed, #3b82f6)', letterSpacing: 1 }}>
          <Sparkles size={16} /> SIMULAR A CIDADE CONECTADA
        </Link>
        <span className="font-mono" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, color: '#f87171', letterSpacing: 2 }}>
          <span className="ap-ponto-vivo" /> AO VIVO
        </span>
        <Relogio agora={agora} />
      </header>

      <div style={{ display: 'flex', gap: 12 }}>
        <Kpi rotulo="VEÍCULOS ATIVOS" valor={veiculosAtivos} detalhe={`foto nos últimos ${JANELA_MIN} min`} />
        <Kpi rotulo="CÂMERAS FIXAS AO VIVO" valor={`${camerasAoVivo(cameras, agora)}/${cameras.length}`} detalhe="lives públicas e CCTV" />
        <Kpi rotulo="FOTOS DO CARRO" valor={recentes.length} detalhe={`últimos ${JANELA_MIN} min`} />
        <Kpi rotulo="CONFIANÇA MÉDIA" valor={conf != null ? `${conf}%` : '—'} detalhe="modelo do carro" />
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 14 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ flex: 1, minHeight: 0, borderRadius: 16, overflow: 'hidden', border: '1px solid var(--bg-border)' }}>
            <MapaAoVivo capturas={recentes} ultimaConhecida={ultima} celulas={celulas} chaveEnquadrar="apresentacao" />
          </div>
          <FaixaCameras cameras={cameras} />
        </div>
        <div style={{ width: 460, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
          <CardCarro ultima={ultima} recentes={recentes} agora={agora} />
          <Pipeline pulso={pulso} />
          <Feed itens={feed(recentes, cameras, 7)} />
        </div>
      </div>
    </div>
  )
}
