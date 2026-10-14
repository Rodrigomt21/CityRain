import { Fragment, useEffect, useMemo, useRef } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Circle, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { categoryFromLabel } from '../../lib/categories'
import { BASE_URL } from '../../api/client'
import { resumoCamera, estadoCirculo } from '../../lib/cameras'

const CENTRO_SP = [-23.56, -46.62]


// Acompanha o carro: na primeira carga enquadra câmeras e trajeto; depois segue a posição atual.
function Seguir({ pontos, posCameras }) {
  const map = useMap()
  const enquadrado = useRef(false)
  const enquadrouCameras = useRef(false)
  useEffect(() => {
    const todos = [...pontos.map(p => p.pos), ...posCameras]
    if (!todos.length) return
    // as câmeras chegam por outra requisição: enquadra de novo uma única vez quando aparecem
    const camerasNovas = posCameras.length > 0 && !enquadrouCameras.current
    if (!enquadrado.current || camerasNovas) {
      map.fitBounds(todos, { padding: [60, 60], maxZoom: 16 })
      enquadrado.current = true
      if (posCameras.length) enquadrouCameras.current = true
    } else if (pontos.length) {
      map.panTo(pontos[pontos.length - 1].pos, { animate: true })
    }
  }, [map, pontos, posCameras])
  return null
}

function TooltipCirculo({ nome, estado, captura, imagemSrc }) {
  const { categoria } = estado
  const conf = captura?.confidence != null ? ` · ${Math.round(captura.confidence * 100)}%` : ''
  return (
    <Tooltip sticky>
      {imagemSrc && <img src={imagemSrc} alt="" style={{ display: 'block', width: 160, borderRadius: 4, marginBottom: 4 }} />}
      <b>{nome}</b><br />
      {categoria.label}{conf}{estado.raioM && ` · raio ~${estado.raioM} m`}<br />
      {captura?.captured_at ? new Date(captura.captured_at).toLocaleTimeString('pt-BR') : 'sem captura ainda'}
    </Tooltip>
  )
}

/** Trajeto ao vivo: segmentos coloridos pela classe e posição atual pulsando. */
export default function MapaAoVivo({ capturas, ultimaConhecida, cameras = [] }) {
  const pontos = useMemo(
    () => capturas.map(c => ({ ...c, pos: [c.latitude, c.longitude], cat: categoryFromLabel(c.weather_label) })),
    [capturas],
  )
  const atual = pontos[pontos.length - 1]
  const segmentos = pontos.slice(1).map((p, i) => ({ de: pontos[i].pos, para: p.pos, cor: p.cat.color, id: p.id }))
  const agora = new Date()
  const camerasComPos = cameras.filter(c => c.latitude != null && c.longitude != null)
  const posCameras = useMemo(
    () => cameras.filter(c => c.latitude != null && c.longitude != null).map(c => [c.latitude, c.longitude]),
    [cameras],
  )
  // Jetson: último ponto do trajeto ou, sem trajeto recente, a última posição conhecida
  const carro = atual
    ? { pos: atual.pos, captura: atual }
    : ultimaConhecida ? { pos: [ultimaConhecida.latitude, ultimaConhecida.longitude], captura: ultimaConhecida } : null
  const estadoCarro = carro && estadoCirculo(carro.captura, agora)
  const centro = atual?.pos ?? (ultimaConhecida ? [ultimaConhecida.latitude, ultimaConhecida.longitude] : CENTRO_SP)

  return (
    <MapContainer center={centro} zoom={14} style={{ height: '100%', width: '100%', background: '#0b1220' }}>
      <TileLayer
        className="mapa-escuro"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {camerasComPos.map(c => {
        const r = resumoCamera(c, BASE_URL, agora)
        const estado = estadoCirculo(c.ultima_captura, agora)
        // Círculo em metros = área onde achamos que a classe vale (só com classe recente);
        // o ponto em pixels mantém a câmera visível com o mapa afastado
        return (
          <Fragment key={`cam-${c.id}`}>
            {estado.raioM && (
              <Circle center={[c.latitude, c.longitude]} radius={estado.raioM}
                pathOptions={{ color: estado.cor, weight: 2, fillColor: estado.cor, fillOpacity: 0.25 }}>
                <TooltipCirculo nome={r.nome} estado={estado} captura={c.ultima_captura} imagemSrc={r.imagemSrc} />
              </Circle>
            )}
            <CircleMarker center={[c.latitude, c.longitude]} radius={6}
              pathOptions={{ color: '#0b1220', weight: 2, fillColor: estado.cor, fillOpacity: 1 }}>
              <TooltipCirculo nome={r.nome} estado={estado} captura={c.ultima_captura} imagemSrc={r.imagemSrc} />
            </CircleMarker>
          </Fragment>
        )
      })}
      {carro && estadoCarro.raioM && (
        <Circle center={carro.pos} radius={estadoCarro.raioM}
          pathOptions={{ color: estadoCarro.cor, weight: 2, fillColor: estadoCarro.cor, fillOpacity: 0.25 }}>
          <TooltipCirculo nome="Jetson (carro)" estado={estadoCarro} captura={carro.captura} imagemSrc={null} />
        </Circle>
      )}
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
      <Seguir pontos={pontos} posCameras={posCameras} />
    </MapContainer>
  )
}
