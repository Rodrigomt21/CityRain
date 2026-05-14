import { useNavigate } from 'react-router-dom'
import { Droplets, ArrowRight } from 'lucide-react'

// Gotas uniformes — mesma cor, 1px, espaçamento regular, velocidade lenta
const RAIN_DROPS = Array.from({ length: 50 }, (_, i) => ({
  left: `${(i * 2) % 100}%`,
  height: `${16 + (i % 4) * 6}px`,
  animationDuration: `${1.4 + (i % 5) * 0.3}s`,
  animationDelay: `${(i * 0.18) % 2.5}s`,
}))

const STATS = [
  { value: '20',   label: 'Sensores Ativos' },
  { value: '4',    label: 'Níveis de Alerta' },
  { value: '30s',  label: 'Frequência de Leitura' },
  { value: '24/7', label: 'Monitoramento Contínuo' },
]

export default function Hero() {
  const navigate = useNavigate()

  return (
    <section
      className="relative flex flex-col items-center justify-center overflow-hidden"
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(160deg, #0a0d12 0%, #0d1220 50%, #111620 100%)',
      }}
    >
      {/* Chuva decorativa */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden>
        {RAIN_DROPS.map((drop, i) => (
          <div
            key={i}
            className="absolute animate-rain-fall"
            style={{
              left: drop.left,
              top: 0,
              width: '1px',
              height: drop.height,
              background: 'linear-gradient(to bottom, transparent, #3b82f6)',
              animationDuration: drop.animationDuration,
              animationDelay: drop.animationDelay,
            }}
          />
        ))}
      </div>

      {/* Brilho central suave */}
      <div
        className="absolute pointer-events-none"
        style={{
          width: '700px',
          height: '500px',
          borderRadius: '50%',
          background: 'radial-gradient(ellipse, #3b82f60a 0%, transparent 70%)',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
        }}
        aria-hidden
      />

      <div className="relative z-10 flex flex-col items-center text-center px-6" style={{ maxWidth: '680px' }}>
        {/* Logo */}
        <div className="flex items-center gap-4 mb-6">
          <div
            className="p-3 rounded-2xl"
            style={{
              background: '#3b82f618',
              border: '1px solid #3b82f640',
              boxShadow: '0 0 24px #3b82f620',
            }}
          >
            <Droplets size={36} color="var(--accent-brand)" />
          </div>
          <span
            className="font-mono font-bold"
            style={{ fontSize: '3rem', color: 'var(--text-primary)', letterSpacing: '-0.03em' }}
          >
            City Rain
          </span>
        </div>

        {/* Texto principal */}
        <p
          className="font-sans mb-10"
          style={{ color: 'var(--text-secondary)', fontSize: '1.05rem' }}
        >
          Tecnologia de ponta para operadores de defesa civil
        </p>

        {/* CTA */}
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 px-7 py-3.5 rounded-lg font-mono font-semibold text-sm mb-14"
          style={{
            background: 'var(--accent-brand)',
            color: '#fff',
            border: 'none',
            cursor: 'pointer',
            boxShadow: '0 0 24px #3b82f644, 0 4px 16px #0004',
            transition: 'box-shadow 0.2s, transform 0.15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.boxShadow = '0 0 36px #3b82f666, 0 4px 20px #0006'
            e.currentTarget.style.transform = 'translateY(-1px)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.boxShadow = '0 0 24px #3b82f644, 0 4px 16px #0004'
            e.currentTarget.style.transform = 'translateY(0)'
          }}
        >
          Acessar Dashboard
          <ArrowRight size={16} />
        </button>

        {/* Stats */}
        <div
          className="grid grid-cols-4 w-full rounded-xl"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
        >
          {STATS.map((s, i) => (
            <div
              key={s.label}
              className="flex flex-col items-center py-5"
              style={{ borderRight: i < STATS.length - 1 ? '1px solid var(--bg-border)' : 'none' }}
            >
              <span className="font-mono font-bold mb-1" style={{ fontSize: '1.6rem', color: 'var(--text-primary)' }}>
                {s.value}
              </span>
              <span className="font-sans text-xs" style={{ color: 'var(--text-secondary)' }}>
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
