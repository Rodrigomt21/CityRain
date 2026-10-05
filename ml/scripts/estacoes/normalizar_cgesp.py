"""Normaliza o boletim pluviométrico mensal da CGE-SP (planilha XLSX pública,
publicada em Nextcloud/SAISP) para o schema único da spec F1.1.

Entrada: ml/data/raw/estacoes/respostas_brutas/cgesp/2026-08-PLUVIOMETRIA-CGESP.xlsx
(baixado via WebDAV público, sem autenticação, do compartilhamento
https://arquivos.saisp.br/nextcloud/index.php/s/qikdinFyAM33MJK).

Limitações conhecidas (ver docs/fontes-estacoes.md para detalhes):
- É um TOTAL DIÁRIO (janela_min=1440), não uma leitura fina de 10/60 min.
- O site da CGE-SP não publica lat/lon das estações telemétricas
  (apenas um mapa de imagem estática) — por isso lat/lon ficam em branco
  aqui. NÃO é uma coordenada inventada: é ausência documentada da fonte.
- Só o mês de agosto/2026 estava publicado em 15/09/2026 (atraso de
  publicação) — logo só o dia-alvo 2026-08-04 é coberto por este script.
- ts_utc assume que o total diário cobre a janela do dia civil local
  (00:00-23:59 America/Sao_Paulo), reportado no timestamp de início do dia
  em UTC (03:00Z). Essa é uma suposição documentada, não confirmada pela
  CGE-SP (o "zeramento" real da estação pode ser em outro horário, ex.:
  10:00 local, conforme observado na página ao vivo de uma estação).

Este script é auxiliar de investigação (spec F1.1), não é o cliente de
ingestão de produção (isso é escopo de outra tarefa, F1.2).
"""

from __future__ import annotations

import csv
from pathlib import Path

try:
    import openpyxl
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Este script requer o pacote 'openpyxl' (pip install openpyxl)."
    ) from exc


XLSX_PATH = Path(
    "/Users/rodrigo/Documents/faculdade7Semestre/TCC/code/CityRain/ml/data/raw/"
    "estacoes/respostas_brutas/cgesp/2026-08-PLUVIOMETRIA-CGESP.xlsx"
)
OUT_PATH = Path(
    "/Users/rodrigo/Documents/faculdade7Semestre/TCC/code/CityRain/ml/data/raw/"
    "estacoes/normalizado/cgesp.csv"
)

# Mapeia o prefixo/nome usado no boletim (coluna A) para o POSTO usado no
# site estacoes-meteorologicas.jsp / estacao.jsp?POSTO=<id> (fonte oficial
# do identificador — nao inventado; extraido de
# https://www.cgesp.org/v3/estacoes-meteorologicas.jsp).
# So mapeamos as estacoes proximas a regiao das 3 sessoes (Cambuci / Vila
# Mariana / Mooca), que sao as que interessam a spec.
ESTACOES_RELEVANTES = {
    "SE - Sé": ("503", "Sé - CGE"),
    "MO - Móoca": ("1000860", "Móoca"),
    "IP - Ipiranga": ("1000840", "Ipiranga"),
    "VP - Vila Prudente": ("524", "Vila Prudente"),
    "VM - Vila Mariana": ("495", "Vila Mariana"),
    "JA - Jabaquara": ("634", "Jabaquara"),
}

MES_ANO = "2026-08"
DIA_ALVO = 4  # dia 04/08/2026 - unico dia-alvo coberto pelo boletim de agosto


def main() -> None:
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb["total"]

    linhas_saida = []
    for row in ws.iter_rows(min_row=8, max_row=89, values_only=True):
        nome_boletim = row[0]
        if nome_boletim not in ESTACOES_RELEVANTES:
            continue
        estacao_id, estacao_nome = ESTACOES_RELEVANTES[nome_boletim]
        valor_dia = row[DIA_ALVO]
        if valor_dia is None:
            continue
        ts_utc = f"{MES_ANO}-{DIA_ALVO:02d}T03:00:00Z"  # 00:00 local (UTC-3)
        linhas_saida.append(
            [
                "cgesp",
                estacao_id,
                estacao_nome,
                "",  # lat - nao publicado pela fonte, ver docstring
                "",  # lon - nao publicado pela fonte, ver docstring
                ts_utc,
                valor_dia,
                1440,
            ]
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["fonte", "estacao_id", "estacao_nome", "lat", "lon", "ts_utc", "acumulado_mm", "janela_min"]
        )
        writer.writerows(linhas_saida)

    print(f"Escrito {len(linhas_saida)} linhas em {OUT_PATH}")


if __name__ == "__main__":
    main()
