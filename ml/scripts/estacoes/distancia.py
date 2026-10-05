"""Utilitários de distância geográfica para a spec F1.1 (histórico de estações).

Calcula a distância haversine (km) entre um ponto (estação) e o ponto mais
próximo de um bounding box retangular (bbox) de uma sessão de coleta. Usado
para filtrar estações candidatas num raio de 5 km dos bboxes das 3 sessões-alvo.

Nenhuma coordenada de estação é inventada por este script: as coordenadas
devem vir de uma fonte oficial (catálogo da rede) e ser passadas como entrada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class BBox:
    """Bounding box retangular em graus decimais (WGS84)."""

    nome: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def ponto_mais_proximo(self, lat: float, lon: float) -> tuple[float, float]:
        """Retorna o ponto do bbox mais próximo de (lat, lon).

        Se (lat, lon) já estiver dentro do bbox, retorna o próprio ponto
        (distância zero).
        """
        clamped_lat = min(max(lat, self.lat_min), self.lat_max)
        clamped_lon = min(max(lon, self.lon_min), self.lon_max)
        return clamped_lat, clamped_lon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância haversine em km entre dois pontos WGS84.

    Args:
        lat1: Latitude do ponto 1, em graus decimais.
        lon1: Longitude do ponto 1, em graus decimais.
        lat2: Latitude do ponto 2, em graus decimais.
        lon2: Longitude do ponto 2, em graus decimais.

    Returns:
        Distância em quilômetros.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def distancia_ao_bbox_km(lat: float, lon: float, bbox: BBox) -> float:
    """Distância haversine (km) de (lat, lon) ao ponto mais próximo do bbox."""
    plat, plon = bbox.ponto_mais_proximo(lat, lon)
    return haversine_km(lat, lon, plat, plon)


# As 3 sessões-alvo, conforme docs/specs/spec-historico-estacoes.md.
SESSOES = [
    BBox("2026-08-04", -23.5674, -23.5533, -46.6068, -46.5907),
    BBox("2026-09-01", -23.5657, -23.5466, -46.6593, -46.5880),
    BBox("2026-09-13", -23.5664, -23.5499, -46.6061, -46.5917),
]


def menor_distancia_as_sessoes_km(lat: float, lon: float) -> tuple[str, float]:
    """Retorna (nome_da_sessao_mais_proxima, distancia_km) para uma estação."""
    melhor_nome = ""
    melhor_dist = math.inf
    for bbox in SESSOES:
        d = distancia_ao_bbox_km(lat, lon, bbox)
        if d < melhor_dist:
            melhor_dist = d
            melhor_nome = bbox.nome
    return melhor_nome, melhor_dist


if __name__ == "__main__":
    # Exemplo manual de uso / smoke test.
    exemplos = [
        ("CEMADEN AC Central de SP", -23.54331, -46.63599),
        ("CGE Vila Mariana", None, None),
        ("INMET A701 Mirante de Santana", -23.4962888, -46.6200666),
        ("INMET A771 Interlagos", -23.72444443, -46.67749999),
        ("DAEE Mooca (E3-246)", -23.5667, -46.6167),
    ]
    for nome, lat, lon in exemplos:
        if lat is None:
            continue
        sessao, dist = menor_distancia_as_sessoes_km(lat, lon)
        print(f"{nome}: {dist:.2f} km da sessão {sessao}")
