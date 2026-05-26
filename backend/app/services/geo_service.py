from typing import Any

import h3


class GeoService:
    """Utilitários de geoespacialização usando H3 (Uber)."""

    @staticmethod
    def to_h3_cell(latitude: float, longitude: float, resolution: int = 8) -> str:
        """Converte coordenadas GPS para índice de célula H3."""
        return h3.latlng_to_cell(latitude, longitude, resolution)

    @staticmethod
    def group_by_h3(captures: list[dict[str, Any]], resolution: int = 8) -> list[dict]:
        """
        Agrupa capturas por célula H3 e conta ocorrências por weather_label.

        Retorna lista de dicts com: cell, count, labels (dict label→count).
        Usado pelo endpoint /stats/geo para alimentar o heatmap do dashboard.
        """
        cells: dict[str, dict] = {}

        for capture in captures:
            cell = h3.latlng_to_cell(capture["latitude"], capture["longitude"], resolution)

            if cell not in cells:
                cells[cell] = {"cell": cell, "count": 0, "labels": {}}

            cells[cell]["count"] += 1
            label = capture.get("weather_label") or "unknown"
            cells[cell]["labels"][label] = cells[cell]["labels"].get(label, 0) + 1

        return list(cells.values())
