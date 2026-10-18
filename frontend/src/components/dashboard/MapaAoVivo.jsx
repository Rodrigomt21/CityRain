import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Polygon, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { CATEGORIES, UNMEASURED, categoryFromLabel } from '../../lib/categories'
import { MINUTOS_CIRCULO_FRESCO } from '../../lib/cameras'

const CENTRO_SP = [-23.56, -46.62]

// Acompanha o carro: na primeira carga enquadra dispositivos e trajeto; depois segue a posição atual.
// Mudar `chave` (o filtro fixa/móvel) enquadra de novo o que ficou visível.
function Seguir({ pontos, posDispositivos, chave }) {
  const map = useMap()
  const enquadrado = useRef(false)
  const enquadrouDispositivos = useRef(false)
  const ultimaChave = useRef(chave)
  useEffect(() => {
    if (ultimaChave.current !== chave) {
      ultimaChave.current = chave
      enquadrado.current = false
      enquadrouDispositivos.current = false
      map.invalidateSize() // o painel "Agora" aparece ou some e o mapa muda de largura
    }
    const todos = [...pontos.map(p => p.pos), ...posDispositivos]
    if (!todos.length) return
    // os dispositivos chegam por outra requisição: enquadra de novo uma única vez quando aparecem
    const novos = posDispositivos.length > 0 && !enquadrouDispositivos.current
    if (!enquadrado.current || novos) {
      map.fitBounds(todos, { padding: [60, 60], maxZoom: 15 })
      enquadrado.current = true
      if (posDispositivos.length) enquadrouDispositivos.current = true
    } else if (pontos.length) {
      map.panTo(pontos[pontos.length - 1].pos, { animate: true })
    }
  }, [map, pontos, posDispositivos, chave])
  return null
}

const ORDEM_LEGENDA = ['heavy', 'moderate', 'drizzle', 'dry']

/** Legenda no canto inferior esquerdo: não captura cliques, então não atrapalha arrastar o mapa. */
function Legenda() {
  return (
    <div role="group" aria-label="Legenda do mapa" className="font-mono"
      style={{
        position: 'absolute', left: 10, bottom: 22, zIndex: 1000, pointerEvents: 'none',
        background: 'rgba(11, 18, 32, 0.88)', border: '1px solid var(--bg-border)', borderRadius: 8,
        padding: '8px 10px', fontSize: 12, lineHeight: 1.5, color: 'var(--text-primary)', maxWidth: 240,
      }}>
      <div style={{ color: 'var(--text-secondary)', letterSpacing: 1, marginBottom: 4 }}>CLASSE DA ÚLTIMA FOTO</div>
      {ORDEM_LEGENDA.map(k => (
        <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: CATEGORIES[k].color, flexShrink: 0 }} />
          <span>{CATEGORIES[k].label}</span>
        </div>
      ))}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, paddingTop: 4, borderTop: '1px solid var(--bg-border)' }}>
        <span style={{ width: 10, height: 10, borderRadius: 2, border: `1px dashed ${UNMEASURED.color}`, flexShrink: 0 }} />
        <span>Tracejado · sem dado há mais de {MINUTOS_CIRCULO_FRESCO} min ou sem classe</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
        <span style={{ width: 10, height: 4, borderRadius: 2, background: 'linear-gradient(90deg, #67e8f9, #fb923c)', flexShrink: 0 }} />
        <span style={{ color: 'var(--text-secondary)' }}>Linha · trajeto do carro, cor pela classe</span>
      </div>
      <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>Hexágono H3 ~460 m · clique para ver o último frame</div>
    </div>
  )
}

/**
 * Mapa ao vivo: um hexágono H3 por célula com dispositivo (fixa ou móvel), pintado pela classe da
 * última foto classificada; clique abre o painel da célula. Mantém o trajeto recente do carro.
 */
export default function MapaAoVivo({
  capturas, ultimaConhecida, celulas = [], selecionada = null, onSelecionar = () => {}, chaveEnquadrar = null,
}) {
  const pontos = useMemo(
    () => capturas.map(c => ({ ...c, pos: [c.latitude, c.longitude], cat: categoryFromLabel(c.weather_label) })),
    [capturas],
  )
  const atual = pontos[pontos.length - 1]
  const segmentos = pontos.slice(1).map((p, i) => ({ de: pontos[i].pos, para: p.pos, cor: p.cat.color, id: p.id }))
  const chavesPos = celulas.flatMap(c => c.dispositivos.map(d => `${d.lat},${d.lng}`)).join('|')
  // eslint-disable-next-line react-hooks/exhaustive-deps -- recalcula só quando alguma posição muda
  const posDispositivos = useMemo(() => celulas.flatMap(c => c.dispositivos.map(d => [d.lat, d.lng])), [chavesPos])
  const centro = atual?.pos ?? (ultimaConhecida ? [ultimaConhecida.latitude, ultimaConhecida.longitude] : CENTRO_SP)

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
    <MapContainer center={centro} zoom={14} style={{ height: '100%', width: '100%', background: '#0b1220' }}>
      <TileLayer
        className="mapa-escuro"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {celulas.map(c => {
        const sel = c.celula === selecionada
        const nomes = c.dispositivos.map(d => d.nome).join(' · ')
        return (
          <Polygon key={c.celula} positions={c.contorno}
            eventHandlers={{ click: () => onSelecionar(c.celula) }}
            pathOptions={{
              color: sel ? '#ffffff' : c.estado.cor, weight: sel ? 3 : 2,
              dashArray: c.estado.tracejado ? '6 6' : null,
              fillColor: c.estado.cor, fillOpacity: c.estado.tracejado ? 0.12 : 0.35,
            }}>
            <Tooltip sticky>{nomes} · {c.estado.categoria.label}<br />clique para ver o último frame</Tooltip>
          </Polygon>
        )
      })}
      {/* ponto em pixels: mantém o dispositivo visível com o mapa afastado (o hexágono some no zoom baixo) */}
      {celulas.flatMap(c => c.dispositivos.map(d => (
        <CircleMarker key={d.chave} center={[d.lat, d.lng]} radius={d.tipo === 'fixa' ? 5 : 6}
          eventHandlers={{ click: () => onSelecionar(c.celula) }}
          pathOptions={{ color: '#0b1220', weight: 2, fillColor: d.estado.cor, fillOpacity: 1 }}>
          <Tooltip>{d.nome}</Tooltip>
        </CircleMarker>
      )))}
      {segmentos.map(s => (
        <Polyline key={s.id} positions={[s.de, s.para]} pathOptions={{ color: s.cor, weight: 6, opacity: 0.85 }} />
      ))}
      {pontos.map(p => (
        <CircleMarker key={p.id} center={p.pos} radius={4}
          pathOptions={{ color: '#0b1220', weight: 1, fillColor: p.cat.color, fillOpacity: 1 }}>
          <Tooltip>
            <b>{p.cat.label}</b>{p.confidence != null && ` · ${Math.round(p.confidence * 100)}%`}<br />
            {new Date(p.captured_at).toLocaleTimeString('pt-BR')}
          </Tooltip>
        </CircleMarker>
      ))}
      {atual && (
        <>
          <CircleMarker center={atual.pos} radius={18} className="pulso-ao-vivo"
            pathOptions={{ color: atual.cat.color, weight: 2, fillColor: atual.cat.color, fillOpacity: 0.15 }} />
          <CircleMarker center={atual.pos} radius={8}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: atual.cat.color, fillOpacity: 1 }} />
        </>
      )}
      {!atual && ultimaConhecida && (
        <CircleMarker center={[ultimaConhecida.latitude, ultimaConhecida.longitude]} radius={7}
          pathOptions={{ color: '#64748b', weight: 2, fillColor: '#334155', fillOpacity: 1 }}>
          <Tooltip permanent direction="top">Última posição conhecida</Tooltip>
        </CircleMarker>
      )}
      <Seguir pontos={pontos} posDispositivos={posDispositivos} chave={chaveEnquadrar} />
    </MapContainer>
    <Legenda />
    </div>
  )
}
