from typing import Any

import h3


class GeoService:
    """Utilitários de geoespacialização usando H3 (Uber)."""

    # Resolução em que h3_cell é gravada na ingestão (~70 m de aresta).
    # Resoluções mais grossas são derivadas via cell_to_parent; mais finas
    # que isso são impossíveis de derivar — o endpoint limita o parâmetro.
    H3_BASE_RESOLUTION = 10

    @staticmethod
    def to_h3_cell(latitude: float, longitude: float, resolution: int = H3_BASE_RESOLUTION) -> str:
        """Converte coordenadas GPS para índice de célula H3."""
        return h3.latlng_to_cell(latitude, longitude, resolution)

    @staticmethod
    def aggregate_cells(rows: list[tuple[str, str, int]], resolution: int) -> list[dict[str, Any]]:
        """
        Reagrupa contagens por célula base em células da resolução pedida.

        Recebe linhas (h3_cell_base, weather_label, count) já agregadas pelo
        banco (GROUP BY) e converte cada célula base para sua célula-pai na
        resolução do dashboard, somando as contagens.

        Retorna lista de dicts com: cell, count, labels (dict label→count).
        """
        cells: dict[str, dict] = {}

        for base_cell, label, count in rows:
            cell = h3.cell_to_parent(base_cell, resolution)
            if cell not in cells:
                cells[cell] = {"cell": cell, "count": 0, "labels": {}}
            cells[cell]["count"] += count
            label = label or "unknown"
            cells[cell]["labels"][label] = cells[cell]["labels"].get(label, 0) + count

        return list(cells.values())
