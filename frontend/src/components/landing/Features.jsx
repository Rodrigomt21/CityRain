import { CloudRain, Map, AlertTriangle, Activity, Shield, Clock } from 'lucide-react'

const FEATURES = [
  {
    icon: CloudRain,
    title: 'Detecção em Tempo Real',
    description: 'Leituras a cada 30 segundos de múltiplos sensores distribuídos pela cidade, com correlação espacial entre bairros adjacentes.',
    borderColor: 'var(--cat-dry)',
  },
  {
    icon: Map,
    title: 'Cobertura Geoespacial',
    description: 'Visualização interativa dos 20 sensores por bairro com código de cor por intensidade de precipitação e hover com dados detalhados.',
    borderColor: 'var(--cat-drizzle)',
  },
  {
    icon: AlertTriangle,
    title: 'Alertas Operacionais',
    description: 'Notificações imediatas ao exceder limiares críticos, com ordenação por severidade e histórico auditável das últimas 6 horas.',
    borderColor: 'var(--cat-heavy)',
  },
  {
    icon: Activity,
    title: 'Histórico Temporal',
    description: 'Gráfico contínuo das últimas 2 horas com linhas de referência por categoria e área preenchida para identificar tendências.',
    borderColor: 'var(--cat-moderate)',
  },
  {
    icon: Shield,
    title: 'Confiabilidade Operacional',
    description: 'Monitoramento do status de cada sensor com identificação imediata de dispositivos offline para garantir cobertura total.',
    borderColor: 'var(--accent-brand)',
  },
  {
    icon: Clock,
    title: 'Registro Auditável',
    description: 'Tabela de leituras com timestamp preciso, paginação e animação de novos eventos para rastreabilidade completa das ocorrências.',
    borderColor: 'var(--cat-dry)',
  },
]

const STEPS = [
  {
    n: '01',
    title: 'Sensores coletam dados',
    desc: 'Cada sensor pluviométrico registra a intensidade de chuva local a cada 30 segundos e transmite para o sistema central.',
  },
  {
    n: '02',
    title: 'Sistema classifica e alerta',
    desc: 'O algoritmo classifica a leitura em uma das 4 categorias de risco e dispara alertas automáticos ao ultrapassar limiares.',
  },
  {
    n: '03',
    title: 'Operador toma decisão',
    desc: 'O dashboard apresenta todos os dados de forma clara para que o operador de defesa civil possa agir com rapidez e precisão.',
  },
]

const CATEGORIES = [
  { key: 'Seco',     range: '< 0.1 mm/h',  color: '#22c55e', desc: 'Sem precipitação detectada. Condições normais de operação.' },
  { key: 'Garoa',    range: '0.1 – 5 mm/h', color: '#67e8f9', desc: 'Precipitação leve. Monitoramento contínuo recomendado.' },
  { key: 'Moderada', range: '5 – 25 mm/h',  color: '#fb923c', desc: 'Chuva moderada. Atenção a pontos de alagamento conhecidos.' },
  { key: 'Forte',    range: '> 25 mm/h',    color: '#ef4444', desc: 'Chuva intensa. Acionar protocolo de emergência imediatamente.' },
]

export default function Features() {
  return (
    <>
      {/* Funcionalidades */}
      <section
        className="py-20 px-6"
        style={{ background: 'var(--bg-surface)', borderTop: '1px solid var(--bg-border)' }}
      >
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <span
              className="font-mono text-xs uppercase tracking-widest"
              style={{ color: 'var(--accent-brand)' }}
            >
              Plataforma
            </span>
            <h2
              className="font-mono font-bold mt-2"
              style={{ fontSize: '1.6rem', color: 'var(--text-primary)' }}
            >
              Tudo que você precisa numa tela
            </h2>
            <p className="font-sans mt-3 text-sm" style={{ color: 'var(--text-secondary)', maxWidth: '440px', margin: '12px auto 0' }}>
              Um dashboard pensado para operadores sob pressão — denso em informação, zero em ruído.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {FEATURES.map(({ icon: Icon, title, description, borderColor }) => (
              <div
                key={title}
                className="p-5 rounded-lg"
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--bg-border)',
                  borderLeft: `3px solid ${borderColor}`,
                }}
              >
                <div
                  className="flex items-center justify-center w-9 h-9 rounded-lg mb-4"
                  style={{ background: `${borderColor}18`, border: `1px solid ${borderColor}30` }}
                >
                  <Icon size={18} color={borderColor} />
                </div>
                <h3 className="font-mono font-semibold text-sm mb-2" style={{ color: 'var(--text-primary)' }}>
                  {title}
                </h3>
                <p className="font-sans text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  {description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Como funciona */}
      <section
        className="py-20 px-6"
        style={{ background: 'var(--bg-base)', borderTop: '1px solid var(--bg-border)' }}
      >
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <span className="font-mono text-xs uppercase tracking-widest" style={{ color: 'var(--accent-brand)' }}>
              Fluxo Operacional
            </span>
            <h2 className="font-mono font-bold mt-2" style={{ fontSize: '1.6rem', color: 'var(--text-primary)' }}>
              Como funciona
            </h2>
          </div>

          <div className="grid grid-cols-3 gap-6 relative">
            {/* Linha conectora */}
            <div
              className="absolute"
              style={{
                top: '28px',
                left: 'calc(16.66% + 16px)',
                right: 'calc(16.66% + 16px)',
                height: '1px',
                background: 'linear-gradient(to right, var(--cat-drizzle)44, var(--accent-brand)44, var(--cat-heavy)44)',
              }}
              aria-hidden
            />

            {STEPS.map(({ n, title, desc }, i) => {
              const colors = ['var(--cat-drizzle)', 'var(--accent-brand)', 'var(--cat-heavy)']
              const c = colors[i]
              return (
                <div key={n} className="flex flex-col items-center text-center relative">
                  <div
                    className="flex items-center justify-center w-14 h-14 rounded-full font-mono font-bold text-lg mb-4 relative z-10"
                    style={{
                      background: `${c}18`,
                      border: `2px solid ${c}55`,
                      color: c,
                      boxShadow: `0 0 16px ${c}22`,
                    }}
                  >
                    {n}
                  </div>
                  <h3 className="font-mono font-semibold text-sm mb-2" style={{ color: 'var(--text-primary)' }}>
                    {title}
                  </h3>
                  <p className="font-sans text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    {desc}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Categorias de intensidade */}
      <section
        className="py-20 px-6"
        style={{ background: 'var(--bg-surface)', borderTop: '1px solid var(--bg-border)' }}
      >
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <span className="font-mono text-xs uppercase tracking-widest" style={{ color: 'var(--accent-brand)' }}>
              Escala de Risco
            </span>
            <h2 className="font-mono font-bold mt-2" style={{ fontSize: '1.6rem', color: 'var(--text-primary)' }}>
              Categorias de Intensidade
            </h2>
            <p className="font-sans mt-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
              Classificação padronizada para comunicação entre equipes
            </p>
          </div>

          <div className="grid grid-cols-4 gap-4">
            {CATEGORIES.map(({ key, range, color, desc }) => (
              <div
                key={key}
                className="p-5 rounded-lg flex flex-col"
                style={{
                  background: 'var(--bg-card)',
                  border: `1px solid ${color}33`,
                  boxShadow: `0 0 20px ${color}10`,
                }}
              >
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                  />
                  <span
                    className="font-mono font-bold text-sm uppercase tracking-wider"
                    style={{ color }}
                  >
                    {key}
                  </span>
                </div>
                <span
                  className="font-mono text-xs mb-3 px-2 py-1 rounded self-start"
                  style={{ background: `${color}18`, color, border: `1px solid ${color}33` }}
                >
                  {range}
                </span>
                <p className="font-sans text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  {desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}
