import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Droplets, Maximize, Sparkles } from 'lucide-react'
import { Pipeline } from '../components/landing/PipelineAnimado'
import { SIMULACAO_DO_TELAO } from '../lib/telao'

// Telão do estande (EUREKA): a animação do pipeline em loop, grande, com o QR do site.
// As etapas trocam na mão (→/espaço avança, ← volta). S abre a cidade conectada, que volta para cá
// com Esc ou sozinha quando fica parada.

function telaCheia() {
  const el = document.documentElement
  if (document.fullscreenElement) document.exitFullscreen?.()
  else el.requestFullscreen?.().catch(() => {})
}

export default function Telao() {
  const navigate = useNavigate()

  useEffect(() => {
    const tecla = e => {
      if (e.key === 's' || e.key === 'S') navigate(SIMULACAO_DO_TELAO)
      if (e.key === 'f' || e.key === 'F') telaCheia()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [navigate])

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)', padding: 'clamp(16px, 2.2vw, 40px)', gap: 'clamp(16px, 2vw, 32px)' }}>
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Droplets size={34} color="var(--accent-brand)" />
          <span className="font-mono font-bold" style={{ fontSize: 'clamp(22px, 2.2vw, 40px)' }}>CityRain</span>
          <span className="hidden md:inline font-sans" style={{ fontSize: 'clamp(14px, 1.2vw, 22px)', color: 'var(--text-secondary)', marginLeft: 12 }}>
            Do para-brisa ao mapa, em segundos
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={telaCheia} title="Tela cheia (F)" aria-label="Tela cheia"
            className="rounded-lg" style={{ padding: 10, background: 'transparent', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <Maximize size={18} />
          </button>
          <button type="button" onClick={() => navigate(SIMULACAO_DO_TELAO)} title="Cidade conectada (S)"
            className="flex items-center gap-2 rounded-lg font-mono font-semibold"
            style={{ padding: '10px 16px', background: 'var(--accent-brand)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 'clamp(13px, 1vw, 18px)' }}>
            <Sparkles size={16} /> Cidade conectada
          </button>
        </div>
      </header>

      <main className="flex-1 flex items-center">
        <div className="w-full mx-auto" style={{ maxWidth: 'min(100%, calc((100vh - 400px) * 2.1))' }}>
          <Pipeline grande manual />
        </div>
      </main>

      <footer className="flex items-center justify-between gap-6">
        <p className="font-sans" style={{ fontSize: 'clamp(15px, 1.4vw, 26px)', color: 'var(--text-secondary)', margin: 0, maxWidth: 900, lineHeight: 1.4 }}>
          São Paulo tem 1.522 km² e só 110 pluviômetros. A gente transforma câmeras em sensores de chuva.
        </p>
        <div className="flex items-center gap-4 shrink-0">
          <span className="hidden sm:block font-mono text-right" style={{ fontSize: 'clamp(13px, 1.1vw, 20px)', lineHeight: 1.4 }}>
            Abra no celular<br /><b>cityrain.vercel.app</b>
          </span>
          <img src="/qr-site.svg" alt="QR code para cityrain.vercel.app" width={370} height={370}
            style={{ width: 'clamp(84px, 8vw, 150px)', height: 'auto', background: '#fff', padding: 8, borderRadius: 10 }} />
        </div>
      </footer>
    </div>
  )
}
