import { CloudRain, Map, Hexagon, Activity, Cpu, Car } from 'lucide-react'

// Cada item descreve algo que existe hoje no sistema. Prometer tela que não
// existe (alerta automático, tabela paginada) é o que estava errado aqui antes.
const FEATURES = [
  {
    icon: CloudRain,
    title: 'Intensidade pela Imagem',
    description: 'A rede neural lê o frame da câmera e classifica a chuva em quatro níveis. Nenhum pluviômetro a bordo.',
    borderColor: 'var(--cat-dry)',
  },
  {
    icon: Cpu,
    title: 'Processamento na Borda',
    description: 'A Jetson Nano decide se está chovendo ainda dentro do carro. Frame seco é descartado ali mesmo e não gasta rede.',
    borderColor: 'var(--accent-brand)',
  },
  {
    icon: Map,
    title: 'Trajeto ao Vivo',
    description: 'O mapa segue o veículo pela cidade e pinta o caminho dos últimos 30 minutos conforme a intensidade de cada ponto.',
    borderColor: 'var(--cat-drizzle)',
  },
  {
    icon: Hexagon,
    title: 'Agregação Hexagonal',
    description: 'Cada captura cai numa célula H3. O mapa mostra a chuva por região, não pontos soltos.',
    borderColor: 'var(--cat-moderate)',
  },
  {
    icon: Activity,
    title: 'Série Temporal',
    description: 'Quantas capturas de cada classe ao longo do tempo, com recortes de 24 horas a 30 dias.',
    borderColor: 'var(--cat-heavy)',
  },
  {
    icon: Car,
    title: 'Frota de Dispositivos',
    description: 'Quais dispositivos estão registrados, em que veículo e quando cada um reportou pela última vez.',
    borderColor: 'var(--cat-dry)',
  },
]

const STEPS = [
  {
    n: '01',
    title: 'A câmera captura',
    desc: 'O carro percorre São Paulo e o ABC registrando frames com GPS e horário. A Jetson separa chuva de tempo seco ali mesmo.',
  },
  {
    n: '02',
    title: 'O modelo classifica',
    desc: 'Os frames com chuva sobem para o servidor, onde a rede neural estima se é garoa, moderada ou forte.',
  },
  {
    n: '03',
    title: 'O painel agrega',
    desc: 'O dashboard desenha o trajeto, agrupa as capturas em células H3 e mostra como a chuva evoluiu no tempo.',
  },
]

// As faixas em mm/h são a régua usada para ROTULAR o dataset a partir das
// estações públicas (mesmos cortes de ml/configs/rotulagem_imt.yaml). O modelo
// devolve a classe, não o milímetro: mudar aqui sem mudar lá faz a página
// contradizer o modelo.
const CATEGORIES = [
  { key: 'Seco',     range: '0 mm/h',        color: '#22c55e', desc: 'Sem precipitação. O classificador na borda descarta o frame antes do envio.' },
  { key: 'Garoa',    range: '0 – 2,5 mm/h',  color: '#67e8f9', desc: 'Precipitação leve, com pouca alteração visível na via.' },
  { key: 'Moderada', range: '2,5 – 10 mm/h', color: '#fb923c', desc: 'Chuva moderada. Degradação perceptível da visibilidade na imagem.' },
  { key: 'Forte',    range: '> 10 mm/h',     color: '#ef4444', desc: 'Chuva intensa, associada a risco de alagamento na região.' },
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
              Um dashboard pensado para operadores sob pressão: denso em informação, zero em ruído.
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
            <p className="font-sans mt-3 text-sm" style={{ color: 'var(--text-secondary)', maxWidth: '560px', margin: '12px auto 0', lineHeight: 1.6 }}>
              As faixas em mm/h vêm das estações públicas (CGE-SP, INMET, CEMADEN) e servem
              para rotular o dataset. Em operação o modelo vê só a imagem e devolve a classe.
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
