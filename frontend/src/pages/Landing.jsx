import { useNavigate } from 'react-router-dom'
import { Droplets, ArrowRight } from 'lucide-react'
import Hero from '../components/landing/Hero'
import Features from '../components/landing/Features'

function CallToAction() {
  const navigate = useNavigate()
  return (
    <section
      className="py-20 px-6 flex flex-col items-center text-center"
      style={{ background: 'var(--bg-base)', borderTop: '1px solid var(--bg-border)' }}
    >
      <Droplets size={32} color="var(--accent-brand)" className="mb-5" />
      <h2
        className="font-mono font-bold mb-4"
        style={{ fontSize: '1.6rem', color: 'var(--text-primary)' }}
      >
        Pronto para monitorar sua cidade?
      </h2>
      <p className="font-sans text-sm mb-8" style={{ color: 'var(--text-secondary)', maxWidth: '400px' }}>
        Acesse o dashboard operacional e veja os dados de precipitação em tempo real para todos os bairros monitorados.
      </p>
      <button
        onClick={() => navigate('/dashboard')}
        className="flex items-center gap-2 px-7 py-3.5 rounded-lg font-mono font-semibold text-sm"
        style={{
          background: 'var(--accent-brand)',
          color: '#fff',
          border: 'none',
          cursor: 'pointer',
          boxShadow: '0 0 24px #3b82f644',
          transition: 'box-shadow 0.2s, transform 0.15s',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.boxShadow = '0 0 36px #3b82f666'
          e.currentTarget.style.transform = 'translateY(-1px)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.boxShadow = '0 0 24px #3b82f644'
          e.currentTarget.style.transform = 'translateY(0)'
        }}
      >
        Acessar Dashboard
        <ArrowRight size={16} />
      </button>
    </section>
  )
}

export default function Landing() {
  return (
    <div style={{ background: 'var(--bg-base)' }}>
      <Hero />
      <Features />
      <CallToAction />
      <footer
        className="py-6 px-6 font-sans text-xs"
        style={{ background: 'var(--bg-surface)', borderTop: '1px solid var(--bg-border)' }}
      >
        <div
          className="max-w-5xl mx-auto flex items-center justify-between"
          style={{ color: 'var(--text-secondary)' }}
        >
          <div className="flex items-center gap-2">
            <Droplets size={14} color="var(--accent-brand)" />
            <span className="font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>City Rain</span>
            <span>© 2025</span>
          </div>
          <span>Defesa Civil Tech — Fase 1: Visualização com Dados Mock</span>
        </div>
      </footer>
    </div>
  )
}
