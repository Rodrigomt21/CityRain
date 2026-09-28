"""Normaliza dados horários do INMET (ZIP anual de `dadoshistoricos`) para o
schema único da spec F1.1: fonte,estacao_id,estacao_nome,lat,lon,ts_utc,
acumulado_mm,janela_min.

Entrada: os CSVs brutos extraídos do ZIP anual público
(https://portal.inmet.gov.br/uploads/dadoshistoricos/<ano>.zip), já salvos em
ml/data/raw/estacoes/respostas_brutas/inmet/extracted/.

A coluna "Hora UTC" do INMET já vem em UTC (documentado no próprio arquivo e
confirmado manualmente) — não há conversão de fuso a fazer aqui, apenas
formatação para ISO 8601.

Este script é auxiliar de investigação (spec F1.1), não faz parte do cliente
de ingestão de produção (isso é escopo de outra tarefa, F1.2).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


RAW_DIR = Path(
    "/Users/rodrigo/Documents/faculdade7Semestre/TCC/code/CityRain/ml/data/raw/"
    "estacoes/respostas_brutas/inmet/extracted"
)
OUT_PATH = Path(
    "/Users/rodrigo/Documents/faculdade7Semestre/TCC/code/CityRain/ml/data/raw/"
    "estacoes/normalizado/inmet.csv"
)

# Estações e coordenadas conforme catálogo oficial INMET (apitempo.inmet.gov.br/estacoes/T).
ESTACOES = {
    "A701": {
        "arquivo": "INMET_SE_SP_A701_SAO PAULO - MIRANTE_01-01-2026_A_31-08-2026.CSV",
        "nome": "SAO PAULO - MIRANTE (Mirante de Santana)",
        "lat": -23.4962888,
        "lon": -46.6200666,
    },
    "A771": {
        "arquivo": "INMET_SE_SP_A771_SAO PAULO - INTERLAGOS_01-01-2026_A_31-08-2026.CSV",
        "nome": "SAO PAULO - INTERLAGOS",
        "lat": -23.72444443,
        "lon": -46.67749999,
    },
}

# Só há publicação até 31/08/2026 no ZIP de 2026 (baixado em 15/09/2026) —
# logo, dos 3 dias-alvo, só 2026-08-04 está coberto.
DIAS_ALVO = {"2026/08/04", "2026/09/01", "2026/09/13"}


@dataclass(frozen=True)
class Leitura:
    fonte: str
    estacao_id: str
    estacao_nome: str
    lat: float
    lon: float
    ts_utc: str
    acumulado_mm: str
    janela_min: int


def parse_arquivo(codigo: str, info: dict) -> list[Leitura]:
    """Extrai as leituras de precipitação horária para os dias-alvo."""
    path = RAW_DIR / info["arquivo"]
    leituras: list[Leitura] = []
    with path.open(encoding="latin-1") as f:
        linhas = f.readlines()
    for linha in linhas[9:]:  # pula 9 linhas de cabeçalho/metadados
        campos = linha.strip().split(";")
        if len(campos) < 3:
            continue
        data, hora_utc, precip = campos[0], campos[1], campos[2]
        if data not in DIAS_ALVO:
            continue
        if not precip.strip():
            continue  # leitura ausente (gap na estação) — não inventar valor
        hhmm = hora_utc.replace(" UTC", "").zfill(4)
        ts_iso = f"{data.replace('/', '-')}T{hhmm[:2]}:{hhmm[2:]}:00Z"
        precip_norm = precip.replace(",", ".")
        leituras.append(
            Leitura(
                fonte="inmet",
                estacao_id=codigo,
                estacao_nome=info["nome"],
                lat=info["lat"],
                lon=info["lon"],
                ts_utc=ts_iso,
                acumulado_mm=precip_norm,
                janela_min=60,
            )
        )
    return leituras


def main() -> None:
    todas: list[Leitura] = []
    for codigo, info in ESTACOES.items():
        todas.extend(parse_arquivo(codigo, info))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "fonte",
                "estacao_id",
                "estacao_nome",
                "lat",
                "lon",
                "ts_utc",
                "acumulado_mm",
                "janela_min",
            ]
        )
        for l in todas:
            writer.writerow(
                [l.fonte, l.estacao_id, l.estacao_nome, l.lat, l.lon, l.ts_utc, l.acumulado_mm, l.janela_min]
            )

    print(f"Escrito {len(todas)} linhas em {OUT_PATH}")
    dias_cobertos = sorted({l.ts_utc[:10] for l in todas})
    print(f"Dias cobertos (UTC): {dias_cobertos}")


if __name__ == "__main__":
    main()
