"""Normaliza dados do endpoint `horario` do backend do Mapa Interativo do
CEMADEN (mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/
<idEstacao>/<horas>) para o schema único da spec F1.1.

IMPORTANTE — leia antes de usar estes dados como rótulo de verdade:

Este NÃO é o webservice oficial documentado do CEMADEN (PED/SWS, que exige
token JWT obtido via cadastro em https://ped.cemaden.gov.br). É o backend
JSON usado pelo widget de gráfico do Mapa Interativo público
(mapainterativo.cemaden.gov.br), descoberto por engenharia reversa do JS do
site (`script.js` / `grafico_pcds.php`). Ele não exige login nem captcha e
cobre uma janela de até ~360h (~15 dias) antes do momento da consulta — por
isso, dos 3 dias-alvo, só 2026-09-01 e 2026-09-13 estão dentro da janela
quando consultado em 2026-09-15 (2026-08-04 fica fora do alcance).

Duas ressalvas sérias sobre o campo "acumulado_mm" desta fonte:

1. Semântica da janela de acumulação NÃO confirmada. Os valores sobem,
   platôam e decaem ao longo de várias horas de um jeito consistente com
   algum tipo de acumulado corrente (ex.: "chuva acumulada nas últimas 24h,
   recalculada a cada hora") e NÃO com um delta limpo de precipitação da
   própria hora (que seria o ideal para rotulagem). Os valores aqui devem
   ser tratados como um INDÍCIO qualitativo de chuva, não como um valor de
   precipitação horária pronto para uso como rótulo fino.
2. Fuso horário dos rótulos de hora ("0h".."23h"): confirmado empiricamente
   como UTC (o último valor não-nulo do dia corrente bateu com a hora UTC
   atual do sistema no momento da coleta — ver docs/fontes-estacoes.md).
   Ainda assim, como o rótulo "Xh" pode significar o início OU o fim do
   intervalo, o alinhamento exato ao minuto não está confirmado.

Por essas duas ressalvas, janela_min é fixado em 60 (cadência real da
série: 1 leitura por hora), mas o significado do "acumulado_mm" fica restrito
a validação qualitativa (E3), não a rotulagem fina de produção.

Este script é auxiliar de investigação (spec F1.1), não é o cliente de
ingestão de produção (isso é escopo de outra tarefa, F1.2).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


RAW_DIR = Path(
    "/Users/rodrigo/Documents/faculdade7Semestre/TCC/code/CityRain/ml/data/raw/"
    "estacoes/respostas_brutas/cemaden"
)
OUT_PATH = Path(
    "/Users/rodrigo/Documents/faculdade7Semestre/TCC/code/CityRain/ml/data/raw/"
    "estacoes/normalizado/cemaden.csv"
)

# idEstacao -> arquivo bruto salvo (horario/<idEstacao>/360).
ESTACOES = [3085, 3177, 3178, 3179, 3610, 3612, 3614, 3615, 3620, 3623, 3624, 3669, 3809, 3815, 4124]

DIAS_ALVO = {"01/09/2026", "13/09/2026"}  # 04/08/2026 fora da janela de 360h a partir de 15/09/2026


def normalizar_estacao(id_estacao: int) -> list[list]:
    path = RAW_DIR / f"horario_{id_estacao}_360.json"
    with path.open(encoding="utf-8") as f:
        dados = json.load(f)

    est = dados["estacao"]
    codigo = est["codEstacao"]
    nome = est["nome"]
    lat = est["latitude"]
    lon = est["longitude"]

    datas = dados["datas"]
    horarios = dados["horarios"]
    acumulados = dados["acumulados"]

    linhas = []
    for dia_str in DIAS_ALVO:
        if dia_str not in datas:
            continue
        idx = datas.index(dia_str)
        row = acumulados[idx]
        dd, mm, yyyy = dia_str.split("/")
        # Um unico bloco de 24 valores nao-nulos consecutivos corresponde as
        # 24 horas UTC do dia (posicao 0 = 0h, posicao 23 = 23h) - ver
        # verificacao empirica de fuso no docstring do modulo.
        valores_reais = [(i, v) for i, v in enumerate(row) if v is not None]
        if not valores_reais:
            continue
        # Reindexa para hora do dia 0-23 assumindo ordem crescente continua.
        for offset, (_, v) in enumerate(valores_reais):
            hora = offset % 24
            ts_utc = f"{yyyy}-{mm}-{dd}T{hora:02d}:00:00Z"
            linhas.append(["cemaden", codigo, nome, lat, lon, ts_utc, v, 60])
    return linhas


def main() -> None:
    todas: list[list] = []
    for id_estacao in ESTACOES:
        todas.extend(normalizar_estacao(id_estacao))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["fonte", "estacao_id", "estacao_nome", "lat", "lon", "ts_utc", "acumulado_mm", "janela_min"]
        )
        writer.writerows(todas)

    print(f"Escrito {len(todas)} linhas em {OUT_PATH}")
    dias_cobertos = sorted({l[5][:10] for l in todas})
    print(f"Dias cobertos (UTC): {dias_cobertos}")


if __name__ == "__main__":
    main()
