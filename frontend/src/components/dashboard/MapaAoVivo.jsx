import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { categoryFromLabel } from '../../lib/categories'

const CENTRO_SP = [-23.56, -46.62]

// Acompanha o carro: na primeira carga enquadra o trajeto; depois segue a posição atual.
function Seguir({ pontos }) {
  const map = useMap()
  const enquadrado = useRef(false)
  useEffect(() => {
    if (!pontos.length) return
    if (!enquadrado.current) {
      map.fitBounds(pontos.map(p => p.pos), { padding: [60, 60], maxZoom: 16 })
      enquadrado.current = true
    } else {
      map.panTo(pontos[pontos.length - 1].pos, { animate: true })
    }
  }, [map, pontos])
  return null
}

/** Trajeto ao vivo: segmentos coloridos pela classe e posição atual pulsando. */
export default function MapaAoVivo({ capturas, ultimaConhecida }) {
  const pontos = useMemo(
    () => capturas.map(c => ({ ...c, pos: [c.latitude, c.longitude], cat: categoryFromLabel(c.weather_label) })),
    [capturas],
  )
  const atual = pontos[pontos.length - 1]
  const segmentos = pontos.slice(1).map((p, i) => ({ de: pontos[i].pos, para: p.pos, cor: p.cat.color, id: p.id }))
  const centro = atual?.pos ?? (ultimaConhecida ? [ultimaConhecida.latitude, ultimaConhecida.longitude] : CENTRO_SP)

  return (
    <MapContainer center={centro} zoom={14} style={{ height: '100%', width: '100%', background: '#0b1220' }}>
      <TileLayer
        className="mapa-escuro"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
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
      <Seguir pontos={pontos} />
    </MapContainer>
  )
}
