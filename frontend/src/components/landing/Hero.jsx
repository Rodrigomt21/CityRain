import { useNavigate } from 'react-router-dom'
import { Droplets, ArrowRight, Sparkles } from 'lucide-react'

// Gotas uniformes: mesma cor, 1px, espaçamento regular, velocidade lenta
const RAIN_DROPS = Array.from({ length: 50 }, (_, i) => ({
  left: `${(i * 2) % 100}%`,
  height: `${16 + (i % 4) * 6}px`,
  animationDuration: `${1.4 + (i % 5) * 0.3}s`,
  animationDelay: `${(i * 0.18) % 2.5}s`,
}))

// Números verificáveis, não promessas: estações públicas de SP (CEMADEN 79, CGE 32, INMET 2 para
// 1.522 km², ver README), as 4 classes do modelo e os 10 s de atualização do painel ao vivo.
const STATS = [
  { value: '113',  label: 'pluviômetros públicos em SP' },
  { value: '13 km²', label: 'por pluviômetro, em média' },
  { value: '4',    label: 'níveis de chuva' },
  { value: '10 s', label: 'para o mapa atualizar' },
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
            style={{ fontSize: 'clamp(2.1rem, 9vw, 3rem)', color: 'var(--text-primary)', letterSpacing: '-0.03em' }}
          >
            CityRain
          </span>
        </div>

        {/* Texto principal: o problema primeiro, depois a proposta */}
        <h1
          className="font-mono font-bold mb-4"
          style={{ fontSize: 'clamp(1.35rem, 5.5vw, 1.9rem)', color: 'var(--text-primary)', lineHeight: 1.25, margin: '0 0 16px' }}
        >
          São Paulo tem 1.522 km² e só 113 pluviômetros.
        </h1>
        <p
          className="font-sans mb-10"
          style={{ color: 'var(--text-secondary)', fontSize: '1.05rem', lineHeight: 1.6 }}
        >
          A chuva forte cai num bairro e não aparece em estação nenhuma. O CityRain transforma câmeras
          (no carro, na rua, ao vivo) em sensores de chuva: a inteligência artificial olha a imagem e diz se
          está seco, garoando, chovendo moderado ou forte, e o mapa mostra onde.
        </p>

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-center gap-3 mb-14">
        <button
          onClick={() => navigate('/apresentacao')}
          className="flex items-center gap-2 px-7 py-3.5 rounded-lg font-mono font-semibold text-sm"
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
          Ver a chuva agora
          <ArrowRight size={16} />
        </button>
        <button
          onClick={() => navigate('/simulacao')}
          className="flex items-center gap-2 px-6 py-3.5 rounded-lg font-mono font-semibold text-sm"
          style={{ background: 'transparent', color: 'var(--text-primary)', border: '1px solid var(--bg-border)', cursor: 'pointer' }}
        >
          <Sparkles size={16} color="var(--accent-brand)" />
          Simular a cidade conectada
        </button>
        </div>

        {/* Stats */}
        <div
          className="grid grid-cols-2 sm:grid-cols-4 w-full rounded-xl overflow-hidden"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
        >
          {STATS.map(s => (
            <div
              key={s.label}
              className="flex flex-col items-center py-5"
              style={{ boxShadow: '1px 1px 0 var(--bg-border)' }}
            >
              <span className="font-mono font-bold mb-1" style={{ fontSize: '1.6rem', color: 'var(--text-primary)' }}>
                {s.value}
              </span>
              <span className="font-sans text-xs px-2" style={{ color: 'var(--text-secondary)' }}>
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
