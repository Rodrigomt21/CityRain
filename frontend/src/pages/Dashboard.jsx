import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Topbar from '../components/layout/Topbar'
import MapaAoVivo from '../components/dashboard/MapaAoVivo'
import PainelAgora from '../components/dashboard/PainelAgora'
import PainelDispositivo from '../components/dashboard/PainelDispositivo'
import { BASE_URL } from '../api/client'
import { useCameras } from '../hooks/useCameras'
import { useLiveCaptures, JANELA_MIN } from '../hooks/useLiveCaptures'
import { useMoveis } from '../hooks/useMoveis'
import { TIPOS_MAPA, celulasH3, dispositivosDoMapa, filtrarPorTipo, tipoDaUrl } from '../lib/dispositivos'

// Ao vivo = capturas reais dos últimos JANELA_MIN minutos, em mapa real.
// (A versão anterior, com mapa esquemático e simulação quando não havia dado,
// não mostrava onde o dispositivo estava nem o trajeto.)
export default function Dashboard() {
  const { recentes, ultima, atualizadoEm, error, pollMs, carregando } = useLiveCaptures()
  const { cameras } = useCameras()
  const { moveis } = useMoveis()
  const [selecionada, setSelecionada] = useState(null)
  // ?tipo=fixa|movel na URL: a escolha sobrevive ao recarregar e dá para mandar o link
  const [params, setParams] = useSearchParams()
  const tipo = tipoDaUrl(params.get('tipo'))
  const mostrarCarro = tipo !== 'fixa'
  const escolherTipo = valor => {
    setSelecionada(null)
    setParams(valor ? { tipo: valor } : {}, { replace: true })
  }
  // recalculado a cada atualização das fontes: a cor depende de "agora" (captura fresca ou velha)
  const celulas = useMemo(
    () => celulasH3(filtrarPorTipo(dispositivosDoMapa(cameras, moveis, BASE_URL), tipo)),
    [cameras, moveis, tipo],
  )
  const celulaAberta = celulas.find(c => c.celula === selecionada) ?? null

  return (
    // no celular a página rola (painel em cima, mapa embaixo); no desktop tudo cabe em 100vh
    <div className="min-h-screen md:h-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      <Topbar breadcrumb="Ao vivo" backTo="/" />
      <main className="flex-1 min-h-0 flex flex-col gap-3 px-3 py-3 md:px-5 md:py-4">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 className="font-mono font-bold" style={{ fontSize: 22, color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}>
              Monitoramento ao vivo
            </h1>
            <p className="text-[13px]" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Intensidade de chuva estimada pelas câmeras do carro e fixas · hexágono H3 por câmera (clique para ver o último frame) ·
              {mostrarCarro && ` trajeto dos últimos ${JANELA_MIN} min ·`}
              {' '}atualiza a cada {Math.round(pollMs / 1000)} s
              {atualizadoEm && ` · última consulta ${atualizadoEm.toLocaleTimeString('pt-BR')}`}
              {error && <span style={{ color: '#ef4444' }}> · API indisponível: {error.message}</span>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Mostrar no mapa:</span>
            <div role="group" aria-label="Tipo de dispositivo no mapa" style={{ display: 'flex', gap: 4 }}>
              {TIPOS_MAPA.map(t => (
                <button key={t.label} type="button" onClick={() => escolherTipo(t.valor)} aria-pressed={t.valor === tipo}
                  className="font-mono text-xs px-3 py-1.5 rounded"
                  style={{ cursor: 'pointer', color: t.valor === tipo ? 'var(--bg-base)' : 'var(--text-secondary)',
                    background: t.valor === tipo ? 'var(--accent-brand)' : 'transparent', border: '1px solid var(--bg-border)' }}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-3.5 flex-1 min-h-0">
          {/* painel "Agora" é do carro: some quando só as câmeras fixas estão no mapa */}
          {mostrarCarro && (
            <div className="w-full md:w-[400px] shrink-0">
              <PainelAgora capturas={recentes} ultima={ultima} janelaMin={JANELA_MIN} />
            </div>
          )}
          <div className="rounded-xl md:flex-1 min-w-0 h-[65vh] md:h-auto order-first md:order-none" style={{ overflow: 'hidden', border: '1px solid var(--bg-border)', position: 'relative' }}>
            {carregando ? (
              <div role="status" aria-label="Carregando mapa" className="skeleton"
                style={{ height: '100%', borderRadius: 0, display: 'grid', placeItems: 'center' }}>
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Carregando mapa…</span>
              </div>
            ) : (
              <>
                <MapaAoVivo capturas={mostrarCarro ? recentes : []} ultimaConhecida={mostrarCarro ? ultima : null}
                  celulas={celulas} selecionada={selecionada} onSelecionar={setSelecionada} chaveEnquadrar={tipo} />
                <PainelDispositivo celula={celulaAberta} onFechar={() => setSelecionada(null)} />
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
