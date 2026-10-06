import { useMemo } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { CATEGORIES, UNMEASURED, categoryFromLabel, SEVERITY_ORDER } from '../../lib/categories'

// Mesma ordem da legenda do Histórico: do mais leve ao mais severo, e "não medido" por último.
const ORDEM = [...SEVERITY_ORDER.slice().reverse(), 'unmeasured']
const corDe = key => (CATEGORIES[key] ?? UNMEASURED).color
const nomeDe = key => (CATEGORIES[key] ?? UNMEASURED).label

// O eixo do tempo se adapta ao período carregado: sem isso, "24 h" viraria uma
// barra só e "30 dias" viraria centenas de barras ilegíveis.
function escala(spanMs) {
  if (spanMs <= 3 * 3600e3) return { ms: 10 * 60e3, fmt: d => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) }
  if (spanMs <= 48 * 3600e3) return { ms: 3600e3, fmt: d => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) }
  return { ms: 24 * 3600e3, fmt: d => d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) }
}

/**
 * Contagem de capturas por classe ao longo do tempo (objetivo "séries temporais"
 * do pré-projeto).
 *
 * O eixo Y é CONTAGEM DE CAPTURAS, não mm/h: o backend classifica em 4 níveis e
 * não estima intensidade quantitativa, então derivar milímetros daqui seria
 * inventar número.
 */
export default function SerieTemporal({ capturas, loading, altura = 150 }) {
  const { dados, rotulo } = useMemo(() => {
    if (!capturas.length) return { dados: [], rotulo: null }

    const tempos = capturas.map(c => new Date(c.captured_at).getTime())
    const ini = Math.min(...tempos)
    const fim = Math.max(...tempos)
    const { ms, fmt } = escala(fim - ini)

    const baldes = new Map()
    for (const c of capturas) {
      const t = new Date(c.captured_at).getTime()
      const chave = Math.floor(t / ms) * ms
      if (!baldes.has(chave)) {
        baldes.set(chave, { t: chave, rotulo: fmt(new Date(chave)), ...Object.fromEntries(ORDEM.map(k => [k, 0])) })
      }
      baldes.get(chave)[categoryFromLabel(c.weather_label).key] += 1
    }

    return {
      dados: [...baldes.values()].sort((a, b) => a.t - b.t),
      rotulo: ms >= 24 * 3600e3 ? 'por dia' : ms >= 3600e3 ? 'por hora' : 'por 10 min',
    }
  }, [capturas])

  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}>
      <div className="flex items-baseline justify-between mb-2" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div>
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)', letterSpacing: 1 }}>
            CAPTURAS AO LONGO DO TEMPO
          </span>
          {rotulo && (
            <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)', opacity: 0.6 }}> · {rotulo}</span>
          )}
        </div>
        <div className="flex" style={{ gap: 10, flexWrap: 'wrap' }}>
          {ORDEM.map(k => (
            <span key={k} className="flex items-center text-xs" style={{ gap: 4, color: 'var(--text-secondary)' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: corDe(k) }} />
              {nomeDe(k)}
            </span>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: 0, height: altura, display: 'grid', placeItems: 'center' }}>
          Carregando…
        </p>
      ) : dados.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: 0, height: altura, display: 'grid', placeItems: 'center' }}>
          Sem capturas no período selecionado.
        </p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={altura}>
            <BarChart data={dados} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid stroke="var(--bg-border)" vertical={false} />
              <XAxis dataKey="rotulo" tick={{ fill: 'var(--text-secondary)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
              <YAxis allowDecimals={false} tick={{ fill: 'var(--text-secondary)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: '#ffffff0d' }}
                contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono' }}
                formatter={(v, k) => [`${v} captura(s)`, nomeDe(k)]}
              />
              {ORDEM.map(k => (
                <Bar key={k} dataKey={k} stackId="classe" fill={corDe(k)} isAnimationActive={false} />
              ))}
            </BarChart>
          </ResponsiveContainer>
          {/* A API devolve no máximo 200 capturas por consulta — dizer isso evita ler
              o gráfico como se fosse o período inteiro quando há mais que isso. */}
          {capturas.length >= 200 && (
            <p className="text-xs" style={{ color: 'var(--text-secondary)', opacity: 0.7, margin: '6px 0 0' }}>
              Mostrando as {capturas.length} capturas mais recentes do período (limite da API).
            </p>
          )}
        </>
      )}
    </div>
  )
}
