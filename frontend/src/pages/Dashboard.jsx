import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Topbar from '../components/layout/Topbar'
import MapaAoVivo from '../components/dashboard/MapaAoVivo'
import PainelAgora from '../components/dashboard/PainelAgora'
import PainelDispositivo from '../components/dashboard/PainelDispositivo'
import { BASE_URL } from '../api/client'
import { useCameras } from '../hooks/useCameras'
import { useLiveCaptures, JANELA_MIN } from '../hooks/useLiveCaptures'
import { useMoveis } from '../hooks/useMoveis'
import { NOME_TIPO, TIPOS_MAPA, celulasH3, dispositivosDoMapa, filtrarPorTipo, tipoDaUrl } from '../lib/dispositivos'

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
    <div style={{ height: '100vh', background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
      <Topbar breadcrumb="Ao vivo" backTo="/" />
      <main style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '16px 20px', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 }}>
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
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0, whiteSpace: 'nowrap' }}>
            <div role="group" aria-label="Tipo de dispositivo no mapa" style={{ display: 'flex', gap: 4, marginRight: 8 }}>
              {TIPOS_MAPA.map(t => (
                <button key={t.label} type="button" onClick={() => escolherTipo(t.valor)} aria-pressed={t.valor === tipo}
                  className="font-mono text-xs px-3 py-1.5 rounded"
                  style={{ cursor: 'pointer', color: t.valor === tipo ? 'var(--bg-base)' : 'var(--text-secondary)',
                    background: t.valor === tipo ? 'var(--accent-brand)' : 'transparent', border: '1px solid var(--bg-border)' }}>
                  {t.label}
                </button>
              ))}
            </div>
            {[['/apresentacao', 'Apresentação →'], ['/historico', 'Histórico →'], ['/dispositivos', `${NOME_TIPO.movel} →`], ['/cameras', `${NOME_TIPO.fixa} →`]].map(([to, txt]) => (
              <Link key={to} to={to} className="flex items-center gap-1.5 font-mono text-xs px-3 py-1.5 rounded no-underline"
                style={{ color: 'var(--accent-brand)', background: '#3b82f61a', border: '1px solid #3b82f633' }}>
                {txt}
              </Link>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>
          {/* painel "Agora" é do carro: some quando só as câmeras fixas estão no mapa */}
          {mostrarCarro && (
            <div style={{ width: 400, flexShrink: 0 }}>
              <PainelAgora capturas={recentes} ultima={ultima} janelaMin={JANELA_MIN} />
            </div>
          )}
          <div className="rounded-xl" style={{ flex: 1, minWidth: 0, overflow: 'hidden', border: '1px solid var(--bg-border)', position: 'relative' }}>
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
