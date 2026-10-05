#!/usr/bin/env python3
"""Gera o manifest de rotulagem frame -> classe de chuva (F1.3 do plano de dataset).

Para cada frame da coleta própria que tenha uma posição GPS suficientemente
recente, procura a estação pluviométrica mais próxima dentro do raio
configurado, agrega a janela de tempo centrada no instante da captura, converte
para mm/h e aplica os limiares do plano (`seco`, `garoa`, `moderada`, `forte`)
com zona morta nas fronteiras.

Fallback por consenso regional (opcional, `rotulagem.consenso_regional` no
config): quando nenhuma estação dentro do raio tem leitura, o frame ainda é
rotulado se todas as estações com leitura num raio maior concordarem na classe
— ver `ConsensoRegional`. A coluna `metodo_rotulo` diz qual das duas regras
gerou cada rótulo, para que os resultados possam ser reportados com e sem ela.

Todo frame com metadados entra no manifest: os que não puderam ser rotulados
saem com a coluna `motivo_exclusao` preenchida, nunca são omitidos em silêncio.

Idade da posição GPS (J8 do `docs/specs/spec-pipeline-jetson.md`): `gps.py`
mantém a última coordenada conhecida quando o fix cai, só marcando `fix: false`.
Um frame nessa situação ainda é rotulável se a posição for recente o bastante —
a 40 km/h, 5 s de defasagem são ~55 m, bem abaixo do raio de casamento com a
estação. Este script aceita esses frames até um limite configurável de idade da
posição (`idade_maxima_posicao_s`), calculado por três fontes possíveis, em
ordem de preferência (ver `calcular_idade_posicao`):
1. fix atual (idade 0);
2. `gps.ultimo_fix_em` (schema 2, ainda não deployado em campo);
3. inferência pela própria sequência de frames da sessão (schema 1, o caso que
   recupera dado já coletado): como `gps.py` só sobrescreve lat/lon quando há
   fix, a idade é estimada pelo frame mais recente e anterior, na mesma sessão
   (pasta + dia), que teve fix — e essa estimativa é conservadora por
   construção (nunca subestima a idade real).

A conversão leitura -> mm/h assume que a coluna de valor da fonte é o INCREMENTO
de precipitação do intervalo (10 min no CEMADEN/PED), e não um acumulado móvel —
confirmado em 18/09/2026, ver docs/fontes-estacoes.md (Adendo 2).

O script é determinístico: não usa aleatoriedade, e a ordenação de saída é fixa
(pasta, arquivo), assim como o desempate entre estações equidistantes
(distância, depois id da estação). Mesmo input ⇒ mesmo output, byte a byte.

Exemplo de uso:
    python ml/scripts/rotulagem/gerar_manifest.py \\
        --config ml/configs/rotulagem_imt.yaml [--raio-km 3] [--dry-run]
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

# `distancia.py` mora no diretório irmão `estacoes/`. A árvore `ml/scripts/` não
# é um pacote instalável, então o caminho é injetado explicitamente em vez de
# duplicar a implementação de haversine aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estacoes"))

from distancia import haversine_km  # noqa: E402

CLASSES = ("seco", "garoa", "moderada", "forte")

MOTIVO_SEM_TIMESTAMP = "sem_timestamp"
MOTIVO_SEM_FIX = "sem_gps_fix"
MOTIVO_POSICAO_DESATUALIZADA = "posicao_desatualizada"
MOTIVO_FORA_DO_RAIO = "sem_estacao_no_raio"
MOTIVO_SEM_LEITURA = "sem_leitura_na_janela"
MOTIVO_ZONA_MORTA = "zona_morta"
MOTIVO_SECO_INCERTO = "seco_incerto"
MOTIVO_SEM_CONSENSO = "sem_consenso_regional"
MOTIVO_POUCAS_ESTACOES = "poucas_estacoes_consenso"

# Fuso local das coletas (RMSP). Sem horário de verão desde 2019, então a
# conversão é estável para todas as sessões do projeto.
FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")
# Dia = [06:00, 18:30) no horário local; fora disso, noite (coluna `periodo`).
INICIO_DIA = time(6, 0)
FIM_DIA = time(18, 30)
PERIODO_DIA = "dia"
PERIODO_NOITE = "noite"

# Como o rótulo de um frame foi obtido (coluna `metodo_rotulo`).
METODO_ESTACAO_PROXIMA = "estacao_proxima"
METODO_CONSENSO_REGIONAL = "consenso_regional"
METODO_CONSENSO_METROPOLITANO = "consenso_metropolitano"

# Origem da idade da posição GPS de um frame (coluna `origem_idade_posicao`),
# em ordem de preferência — ver `calcular_idade_posicao`.
ORIGEM_FIX_ATUAL = "fix_atual"
ORIGEM_ULTIMO_FIX_EM = "ultimo_fix_em"
ORIGEM_INFERIDA_SEQUENCIA = "inferida_sequencia"

COLUNAS_MANIFEST = (
    "arquivo",
    "pasta",
    "evento_id",
    "ts_utc",
    "lat",
    "lon",
    "idade_posicao_s",
    "origem_idade_posicao",
    "estacao_id",
    "estacao_nome",
    "dist_m",
    "mm_h",
    "classe",
    "n_leituras_janela",
    "cobertura_min",
    "n_estacoes_no_raio",
    "metodo_rotulo",
    "estacoes_consenso",
    "motivo_exclusao",
    # Acrescentada no fim (D1) para que as colunas antigas continuem sendo um
    # prefixo exato do schema anterior.
    "periodo",
)


@dataclass(frozen=True)
class Estacao:
    """Estação pluviométrica com posição conhecida.

    Attributes:
        estacao_id: Código da estação na rede de origem.
        nome: Nome legível da estação.
        lat: Latitude em graus decimais (WGS84).
        lon: Longitude em graus decimais (WGS84).
    """

    estacao_id: str
    nome: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Frame:
    """Metadados de um frame capturado pela Jetson.

    Attributes:
        arquivo: Nome do arquivo .jpg correspondente.
        pasta: Pasta de coleta à qual o frame pertence.
        ts: Instante da captura, timezone-aware em UTC; None se ausente.
        lat: Latitude do GPS; None se nunca houve fix nesta sessão. Pode vir de
            um fix atual ou de uma coordenada congelada de um fix anterior
            (`gps.py` mantém o último valor quando o fix cai).
        lon: Longitude do GPS; mesma regra de `lat`.
        idade_posicao_s: Idade estimada da posição acima, em segundos (0.0 para
            fix atual). None quando há posição mas não há como estimar a idade
            (schema 1 sem histórico de fix na sessão). O default 0.0 assume fix
            atual — conveniente para testes que constroem `Frame` diretamente;
            `carregar_frames` sempre define o valor real a partir do metadado.
        origem_idade_posicao: Como `idade_posicao_s` foi obtida — uma de
            `ORIGEM_FIX_ATUAL`, `ORIGEM_ULTIMO_FIX_EM`, `ORIGEM_INFERIDA_SEQUENCIA`,
            ou "" quando não há posição ou idade conhecida.
    """

    arquivo: str
    pasta: str
    ts: datetime | None
    lat: float | None
    lon: float | None
    idade_posicao_s: float | None = 0.0
    origem_idade_posicao: str = ORIGEM_FIX_ATUAL

    @property
    def evento_id(self) -> str:
        """Identificador do evento de coleta (pasta + dia), para split por evento."""
        dia = self.ts.date().isoformat() if self.ts else "sem_data"
        return f"{self.pasta}__{dia}"


@dataclass(frozen=True)
class ConsensoRegional:
    """Parâmetros da rotulagem por consenso regional (fallback da estação próxima).

    Quando não há estação com leitura dentro de `raio_max_km`, o frame ainda
    pode ser rotulado se TODAS as estações com leitura num raio maior caírem na
    mesma classe. A ideia: num campo de chuva homogêneo (todas secas, ou todas
    em garoa) a classe no ponto do frame não depende de qual estação se usa —
    então a distância deixa de ser a fonte de erro dominante. Se qualquer
    estação discordar (ou cair na zona morta), o campo é heterogêneo e a
    classe no frame é desconhecida: o frame é excluído, nunca interpolado.

    Attributes:
        raio_km: Raio dentro do qual todas as estações precisam concordar.
        min_estacoes: Mínimo de estações com leitura na janela para haver
            consenso — com uma só não há o que concordar.
    """

    raio_km: float
    min_estacoes: int
    zona_morta_na_mediana: bool = False
    zero_de_bascula_neutro: bool = False


@dataclass(frozen=True)
class ConsensoMetropolitano:
    """Parâmetros do `seco` sem GPS, por consenso de toda a rede (D1).

    Um frame sem posição mas com horário não pode ser casado com estação
    alguma. Porém, se TODAS as estações da série (a rede inteira da RMSP que o
    projeto baixa) registraram zero em torno do instante, o carro estava no
    seco onde quer que estivesse. A regra é assimétrica de propósito: qualquer
    chuva em qualquer estação invalida o frame, e nunca se rotula `garoa` sem
    posição, porque a intensidade varia em escala de quilômetros.

    Attributes:
        min_estacoes: Mínimo de estações com leitura na janela; com poucas, um
            zero generalizado pode ser só falta de dado.
        janela_min: Meia-largura da janela de verificação, em minutos.
    """

    min_estacoes: int
    janela_min: int


@dataclass
class LinhaManifest:
    """Uma linha do manifest: um frame, rotulado ou com motivo de exclusão."""

    arquivo: str
    pasta: str
    evento_id: str
    ts_utc: str
    lat: float | None
    lon: float | None
    idade_posicao_s: float | None = None
    origem_idade_posicao: str = ""
    estacao_id: str = ""
    estacao_nome: str = ""
    dist_m: float | None = None
    mm_h: float | None = None
    classe: str = ""
    n_leituras_janela: int = 0
    cobertura_min: int = 0
    n_estacoes_no_raio: int = 0
    metodo_rotulo: str = ""
    estacoes_consenso: str = ""
    motivo_exclusao: str = ""
    periodo: str = ""

    def to_row(self) -> dict[str, Any]:
        """Converte a linha em dict pronto para o csv.DictWriter.

        Floats são arredondados em casas fixas para que o arquivo gerado seja
        estável entre execuções e entre máquinas.
        """
        return {
            "arquivo": self.arquivo,
            "pasta": self.pasta,
            "evento_id": self.evento_id,
            "ts_utc": self.ts_utc,
            "lat": "" if self.lat is None else f"{self.lat:.6f}",
            "lon": "" if self.lon is None else f"{self.lon:.6f}",
            "idade_posicao_s": (
                "" if self.idade_posicao_s is None else f"{self.idade_posicao_s:.1f}"
            ),
            "origem_idade_posicao": self.origem_idade_posicao,
            "estacao_id": self.estacao_id,
            "estacao_nome": self.estacao_nome,
            "dist_m": "" if self.dist_m is None else f"{self.dist_m:.1f}",
            "mm_h": "" if self.mm_h is None else f"{self.mm_h:.4f}",
            "classe": self.classe,
            "n_leituras_janela": self.n_leituras_janela,
            "cobertura_min": self.cobertura_min,
            "n_estacoes_no_raio": self.n_estacoes_no_raio,
            "metodo_rotulo": self.metodo_rotulo,
            "estacoes_consenso": self.estacoes_consenso,
            "motivo_exclusao": self.motivo_exclusao,
            "periodo": self.periodo,
        }


@dataclass
class Relatorio:
    """Relatório auditável da execução da rotulagem."""

    config_sha256: str = ""
    timestamp_execucao_utc: str = ""
    raio_max_km: float = 0.0
    janela_min: int = 0
    zona_morta_frac: float = 0.0
    minutos_por_leitura: int = 0
    idade_maxima_posicao_s: float = 0.0
    consenso_raio_km: float | None = None
    consenso_min_estacoes: int | None = None
    janela_seco_min: int | None = None
    consenso_zona_morta_na_mediana: bool | None = None
    consenso_metropolitano_min_estacoes: int | None = None
    consenso_metropolitano_janela_min: int | None = None
    total_frames: int = 0
    total_jpg_sem_json: int = 0
    rotulados: int = 0
    por_classe: dict[str, int] = field(default_factory=dict)
    por_motivo: dict[str, int] = field(default_factory=dict)
    por_origem_idade_posicao: dict[str, int] = field(default_factory=dict)
    por_metodo_rotulo: dict[str, int] = field(default_factory=dict)
    por_evento: dict[str, dict[str, int]] = field(default_factory=dict)
    seco_por_evento_periodo: dict[str, dict[str, int]] = field(default_factory=dict)
    ganho_zona_morta_mediana: dict[str, dict[str, int]] = field(default_factory=dict)
    estacoes_usadas: dict[str, int] = field(default_factory=dict)
    sensibilidade_raio: dict[str, dict[str, int]] = field(default_factory=dict)
    sensibilidade_idade_posicao: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Converte o relatório em dicionário serializável em JSON."""
        return {
            "config_sha256": self.config_sha256,
            "timestamp_execucao_utc": self.timestamp_execucao_utc,
            "parametros": {
                "raio_max_km": self.raio_max_km,
                "janela_min": self.janela_min,
                "zona_morta_frac": self.zona_morta_frac,
                "minutos_por_leitura": self.minutos_por_leitura,
                "idade_maxima_posicao_s": self.idade_maxima_posicao_s,
                "consenso_raio_km": self.consenso_raio_km,
                "consenso_min_estacoes": self.consenso_min_estacoes,
                "janela_seco_min": self.janela_seco_min,
                "consenso_zona_morta_na_mediana": self.consenso_zona_morta_na_mediana,
                "consenso_metropolitano_min_estacoes": (
                    self.consenso_metropolitano_min_estacoes
                ),
                "consenso_metropolitano_janela_min": (
                    self.consenso_metropolitano_janela_min
                ),
            },
            "total_frames": self.total_frames,
            "total_jpg_sem_json": self.total_jpg_sem_json,
            "rotulados": self.rotulados,
            "por_classe": self.por_classe,
            "por_motivo": self.por_motivo,
            "por_origem_idade_posicao": self.por_origem_idade_posicao,
            "por_metodo_rotulo": self.por_metodo_rotulo,
            "por_evento": self.por_evento,
            "seco_por_evento_periodo": self.seco_por_evento_periodo,
            "ganho_zona_morta_mediana": self.ganho_zona_morta_mediana,
            "estacoes_usadas": self.estacoes_usadas,
            "sensibilidade_raio": self.sensibilidade_raio,
            "sensibilidade_idade_posicao": self.sensibilidade_idade_posicao,
        }


def sha256_of_file(path: Path) -> str:
    """Calcula o hash sha256 de um arquivo.

    Args:
        path: Caminho do arquivo.

    Returns:
        Hash sha256 em hexadecimal.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def load_config(config_path: Path) -> tuple[dict[str, Any], str]:
    """Carrega o config YAML e devolve também seu hash.

    Args:
        config_path: Caminho do arquivo YAML.

    Returns:
        Tupla (config carregado como dict, sha256 do arquivo de config).
    """
    config_hash = sha256_of_file(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config, config_hash


def _parse_ts(texto: str) -> datetime | None:
    """Converte um timestamp ISO-8601 (com `Z` ou offset) em datetime UTC aware."""
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _delta_segundos_nao_negativo(ts: datetime, referencia: datetime) -> float | None:
    """Segundos entre `referencia` e `ts`, ou None se `referencia` for posterior.

    Uma referência posterior ao próprio frame é um dado inconsistente (relógio
    ou ordenação quebrados) — o lado seguro é não confiar nela, não inventar
    uma idade negativa.
    """
    delta = (ts - referencia).total_seconds()
    return delta if delta >= 0.0 else None


def calcular_idade_posicao(
    gps: dict[str, Any],
    fix: bool,
    tem_posicao: bool,
    ts: datetime | None,
    ultimo_fix_observado: datetime | None,
) -> tuple[float | None, str]:
    """Calcula a idade da posição GPS de um frame e como ela foi obtida (J8).

    Três fontes possíveis, nesta ordem de preferência:

    1. **Fix atual** (`fix: true`): a posição é do próprio instante da
       captura — idade 0.
    2. **`gps.ultimo_fix_em`** (schema 2, ver `docs/specs/spec-pipeline-jetson.md`
       J8): `gps.py` grava o timestamp do último fix bom e não o apaga quando o
       fix cai, então a idade é a diferença direta entre `ts` e esse timestamp.
    3. **Inferência pela sequência** (schema 1, sem `ultimo_fix_em` — é o caso
       que recupera frames já coletados, sem coletar nada novo): como `gps.py`
       só sobrescreve `latitude`/`longitude` quando há fix, a coordenada de um
       frame sem fix é, por construção, a do último fix da própria sessão. A
       idade é estimada pelo instante do frame mais recente e anterior, na
       mesma sessão (pasta + dia — nunca atravessa esse limite, ver
       `carregar_frames`), que teve `fix: true`.

       Essa inferência é **conservadora por construção**: se algum frame com
       fix estiver faltando na sequência observada (jpg/json de 0 byte, corte
       de energia — ver a sessão de 23/09 em `docs/specs/spec-pipeline-jetson.md`),
       `ultimo_fix_observado` aponta para um fix mais antigo do que o fix real
       que a câmera teve. Isso só pode **superestimar** a idade calculada,
       nunca subestimá-la — e superestimar é o lado seguro: no pior caso um
       frame que ainda seria bom é descartado; nunca um frame com posição já
       defasada demais é aceito.

    Args:
        gps: Dicionário `gps` do metadado do frame (pode ser vazio).
        fix: Se este frame tinha fix válido no instante da captura.
        tem_posicao: Se `gps.latitude`/`gps.longitude` não são nulos — mesmo
            com `fix=false` pode haver uma coordenada congelada de um fix
            anterior; nula significa que o `gps.service` nunca teve fix desde
            que subiu (sem inferência possível).
        ts: Instante da captura (`capturado_em_utc`) já normalizado em UTC;
            None se ausente no metadado.
        ultimo_fix_observado: Timestamp do frame com fix mais recente já
            observado nesta sessão (pasta + dia), estritamente anterior a este
            frame; None se nenhum foi visto ainda.

    Returns:
        Tupla (idade em segundos, origem). É (None, "") quando não há posição
        alguma ou não há como estimar a idade dela.
    """
    if not tem_posicao:
        return None, ""
    if fix:
        return 0.0, ORIGEM_FIX_ATUAL
    if ts is not None:
        ultimo_fix_em = _parse_ts(str(gps.get("ultimo_fix_em", "")))
        if ultimo_fix_em is not None:
            delta = _delta_segundos_nao_negativo(ts, ultimo_fix_em)
            if delta is not None:
                return delta, ORIGEM_ULTIMO_FIX_EM
        if ultimo_fix_observado is not None:
            delta = _delta_segundos_nao_negativo(ts, ultimo_fix_observado)
            if delta is not None:
                return delta, ORIGEM_INFERIDA_SEQUENCIA
    return None, ""


def carregar_leituras(
    csv_path: Path,
) -> tuple[dict[str, Estacao], dict[str, list[tuple[datetime, float]]]]:
    """Lê o CSV normalizado de leituras de estação.

    Espera o schema padrão do projeto:
    `fonte,estacao_id,estacao_nome,lat,lon,ts_utc,acumulado_mm,janela_min`.

    Args:
        csv_path: Caminho do CSV normalizado.

    Returns:
        Tupla (estações por id, séries por id). Cada série é uma lista de
        `(timestamp, incremento_mm)` ordenada por timestamp.

    Raises:
        SystemExit: se o arquivo não existir.
    """
    if not csv_path.is_file():
        sys.exit(f"CSV de leituras não encontrado: {csv_path}")

    estacoes: dict[str, Estacao] = {}
    series: dict[str, list[tuple[datetime, float]]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        for reg in csv.DictReader(f):
            ts = _parse_ts(reg.get("ts_utc", ""))
            if ts is None:
                continue
            try:
                lat = float(reg["lat"])
                lon = float(reg["lon"])
                valor = float(reg["acumulado_mm"])
            except (KeyError, TypeError, ValueError):
                continue
            eid = reg["estacao_id"]
            estacoes.setdefault(
                eid, Estacao(eid, reg.get("estacao_nome", eid), lat, lon)
            )
            series.setdefault(eid, []).append((ts, valor))

    for eid in series:
        series[eid].sort(key=lambda par: par[0])
    return estacoes, series


def carregar_frames(raiz: Path) -> tuple[list[Frame], int]:
    """Lê os metadados JSON dos frames normalizados.

    Percorre `raiz/<pasta>/frame_*.json`. Arquivos auxiliares que começam com
    `_` (ex.: `_normalizacao.json`) são ignorados por construção do glob.

    A idade da posição GPS (J8) é calculada por `calcular_idade_posicao` no
    momento em que cada frame é lido, andando em ordem cronológica dentro de
    cada pasta — os nomes `frame_AAAAMMDD_HHMMSS_mmm` garantem essa ordem por
    construção do glob + sort. A âncora de "último fix observado" é mantida
    por `evento_id` (pasta + dia), nunca por pasta sozinha, para que a
    inferência de idade jamais atravesse a fronteira de uma sessão para outra
    mesmo quando duas sessões de dias diferentes convivem na mesma pasta.

    Args:
        raiz: Diretório raiz das pastas de coleta processadas.

    Returns:
        Tupla (frames ordenados por pasta e arquivo, nº de jpgs sem JSON par).

    Raises:
        SystemExit: se a raiz não existir.
    """
    if not raiz.is_dir():
        sys.exit(f"Raiz de frames não encontrada: {raiz}")

    frames: list[Frame] = []
    jpg_sem_json = 0
    # Última captura com fix observada por sessão (pasta + dia). Como os
    # frames de cada pasta são lidos em ordem cronológica (nomes com
    # timestamp), este dict só cresce "para frente" no tempo, o que é
    # exatamente a garantia de que a inferência do item 3 nunca olha para o
    # futuro nem mistura sessões diferentes.
    ultimo_fix_por_evento: dict[str, datetime] = {}
    for pasta_dir in sorted(p for p in raiz.iterdir() if p.is_dir()):
        jsons = sorted(pasta_dir.glob("frame_*.json"))
        nomes_com_json = {j.stem for j in jsons}
        jpg_sem_json += sum(
            1 for j in pasta_dir.glob("*.jpg") if j.stem not in nomes_com_json
        )
        for caminho in jsons:
            try:
                meta = json.loads(caminho.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            gps = meta.get("gps") or {}
            fix = bool(gps.get("fix"))
            tem_posicao = (
                gps.get("latitude") is not None and gps.get("longitude") is not None
            )
            ts = _parse_ts(str(meta.get("capturado_em_utc", "")))
            dia = ts.date().isoformat() if ts else "sem_data"
            evento_id = f"{pasta_dir.name}__{dia}"

            idade_posicao_s, origem_idade_posicao = calcular_idade_posicao(
                gps=gps,
                fix=fix,
                tem_posicao=tem_posicao,
                ts=ts,
                ultimo_fix_observado=ultimo_fix_por_evento.get(evento_id),
            )
            frames.append(
                Frame(
                    arquivo=meta.get("arquivo", f"{caminho.stem}.jpg"),
                    pasta=pasta_dir.name,
                    ts=ts,
                    lat=float(gps["latitude"]) if tem_posicao else None,
                    lon=float(gps["longitude"]) if tem_posicao else None,
                    idade_posicao_s=idade_posicao_s,
                    origem_idade_posicao=origem_idade_posicao,
                )
            )
            # Atualiza a âncora só DEPOIS de calcular a idade deste frame, para
            # que "último fix observado" nunca inclua o próprio frame atual.
            if fix and tem_posicao and ts is not None:
                ultimo_fix_por_evento[evento_id] = ts
    frames.sort(key=lambda fr: (fr.pasta, fr.arquivo))
    return frames, jpg_sem_json


def intensidade_na_janela(
    serie: list[tuple[datetime, float]],
    centro: datetime,
    janela_min: int,
    minutos_por_leitura: int,
) -> tuple[float | None, int, int]:
    """Agrega a série de uma estação numa janela centrada e devolve a taxa em mm/h.

    A janela é fechada nos dois extremos: `[centro - janela, centro + janela]`.
    Como cada leitura é o incremento de precipitação do seu próprio intervalo, a
    taxa é a média sobre o tempo efetivamente observado — e não sobre a largura
    nominal da janela, que pode não estar toda coberta (em período seco a estação
    transmite de hora em hora, não a cada 10 min).

    Args:
        serie: Leituras `(timestamp, incremento_mm)` ordenadas por timestamp.
        centro: Instante da captura do frame.
        janela_min: Meia-largura da janela, em minutos.
        minutos_por_leitura: Duração do intervalo coberto por uma leitura.

    Returns:
        Tupla (mm/h, nº de leituras na janela, cobertura em minutos). O mm/h é
        None quando não há leitura alguma na janela.
    """
    inicio = centro - timedelta(minutes=janela_min)
    fim = centro + timedelta(minutes=janela_min)
    marcos = [ts for ts, _ in serie]
    i = bisect.bisect_left(marcos, inicio)
    j = bisect.bisect_right(marcos, fim)
    dentro = serie[i:j]
    if not dentro:
        return None, 0, 0
    soma = sum(valor for _, valor in dentro)
    cobertura_min = len(dentro) * minutos_por_leitura
    return soma / (cobertura_min / 60.0), len(dentro), cobertura_min


def classificar(
    mm_h: float, garoa_max: float, moderada_max: float, zona_morta_frac: float
) -> tuple[str, str]:
    """Aplica os limiares do plano com zona morta nas fronteiras.

    Um frame cuja intensidade caia dentro de `±zona_morta_frac` de um limiar é
    descartado em vez de receber um rótulo arbitrário — na fronteira, o ruído da
    báscula e do alinhamento espaço-temporal supera a diferença entre as classes.

    Args:
        mm_h: Intensidade estimada, em mm/h.
        garoa_max: Limiar superior da classe `garoa`.
        moderada_max: Limiar superior da classe `moderada`.
        zona_morta_frac: Fração do limiar que define a zona morta (0.15 = 15%).

    Returns:
        Tupla (classe, motivo_exclusao). Exatamente um dos dois é preenchido.
    """
    if mm_h <= 0.0:
        return "seco", ""
    # Com a zona morta desligada (0.0) a comparação por <= excluiria justamente o
    # valor exatamente igual ao limiar, que é o caso que deveria ser rotulado.
    if zona_morta_frac > 0.0:
        for limiar in (garoa_max, moderada_max):
            if abs(mm_h - limiar) <= zona_morta_frac * limiar:
                return "", MOTIVO_ZONA_MORTA
    # Intervalos fechados à direita, como no plano: garoa 0 < i <= 2,5 ·
    # moderada 2,5 < i <= 10 · forte > 10.
    if mm_h <= garoa_max:
        return "garoa", ""
    if mm_h <= moderada_max:
        return "moderada", ""
    return "forte", ""


def seco_confirmado(
    frame: Frame,
    estacoes: dict[str, Estacao],
    series: dict[str, list[tuple[datetime, float]]],
    raio_km: float,
    janela_seco_min: int,
    minutos_por_leitura: int,
) -> bool:
    """Confirma `seco` exigindo zero em TODAS as estações próximas, numa janela larga.

    Uma estação lendo zero não basta. Em 01/09/2026, os 372 frames rotulados
    `seco` dependiam de uma única leitura de 10 min de AC Central (a 1,5 km)
    enquanto a estação Centro, a 2 km, registrava chuva no mesmo horário, e as
    fotos mostram pista molhada e pedestres de guarda-chuva. A chuva urbana
    varia em escala de 1 a 2 km e o pluviômetro de báscula só registra em
    degraus de 0,2 mm, então "não choveu" é uma afirmação regional: só vale
    se nenhuma estação com leitura dentro de `raio_km` tiver registrado chuva
    em `[ts - janela_seco_min, ts + janela_seco_min]`.

    Args:
        frame: Frame com posição e timestamp.
        estacoes: Estações disponíveis, por id.
        series: Séries de leituras por id de estação.
        raio_km: Raio da verificação (o mesmo do consenso regional).
        janela_seco_min: Meia-largura da janela de verificação, em minutos.
        minutos_por_leitura: Duração do intervalo coberto por uma leitura.

    Returns:
        True se nenhuma estação no raio registrou chuva na janela.
    """
    assert frame.lat is not None and frame.lon is not None and frame.ts is not None
    for est in estacoes.values():
        if haversine_km(frame.lat, frame.lon, est.lat, est.lon) > raio_km:
            continue
        mm_h, _, _ = intensidade_na_janela(
            series.get(est.estacao_id, []), frame.ts, janela_seco_min,
            minutos_por_leitura,
        )
        if mm_h:
            return False
    return True


def periodo_do_dia(ts: datetime | None) -> str:
    """Classifica o instante em `dia` ou `noite` pelo horário local (D1).

    Dia é 06:00 a 18:30 em America/Sao_Paulo. A coluna existe para que o gate
    possa balancear `seco` diurno e noturno: sem isso, um modelo aprenderia
    "escuro => seco" só porque 06/08 e 15/09 foram coletados à noite.

    Args:
        ts: Instante em UTC (aware); None se ausente.

    Returns:
        "dia", "noite", ou "" quando não há timestamp.
    """
    if ts is None:
        return ""
    hora = ts.astimezone(FUSO_LOCAL).time()
    return PERIODO_DIA if INICIO_DIA <= hora < FIM_DIA else PERIODO_NOITE


def _rotular_seco_metropolitano(
    linha: LinhaManifest,
    frame: Frame,
    estacoes: dict[str, Estacao],
    series: dict[str, list[tuple[datetime, float]]],
    metro: ConsensoMetropolitano,
    minutos_por_leitura: int,
) -> None:
    """Rotula `seco` um frame sem posição se a rede inteira estiver zerada (D1).

    Usa todas as estações da série, sem filtro de distância (não há posição).
    Rotula só se houver `metro.min_estacoes` estações com leitura em
    `[ts - janela, ts + janela]` e todas somarem zero. Qualquer chuva, ou poucas
    estações, deixa a linha como está (`sem_gps_fix`). Nunca produz `garoa`.
    """
    assert frame.ts is not None
    leituras: list[tuple[str, float, int, int]] = []
    for est in sorted(estacoes.values(), key=lambda e: e.estacao_id):
        mm_h, n_leituras, cobertura = intensidade_na_janela(
            series.get(est.estacao_id, []), frame.ts, metro.janela_min,
            minutos_por_leitura,
        )
        if mm_h is not None:
            leituras.append((est.estacao_id, mm_h, n_leituras, cobertura))
    if len(leituras) < metro.min_estacoes:
        return
    if any(mm_h > 0.0 for _, mm_h, _, _ in leituras):
        return
    linha.classe = "seco"
    linha.motivo_exclusao = ""
    linha.metodo_rotulo = METODO_CONSENSO_METROPOLITANO
    linha.estacao_nome = "(consenso metropolitano)"
    linha.estacoes_consenso = ";".join(eid for eid, *_ in leituras)
    linha.mm_h = 0.0
    linha.n_leituras_janela = sum(n for _, _, n, _ in leituras)
    linha.cobertura_min = min(c for *_, c in leituras)


def rotular_frame(
    frame: Frame,
    estacoes: dict[str, Estacao],
    series: dict[str, list[tuple[datetime, float]]],
    raio_max_km: float,
    janela_min: int,
    minutos_por_leitura: int,
    garoa_max: float,
    moderada_max: float,
    zona_morta_frac: float,
    idade_maxima_posicao_s: float = float("inf"),
    consenso: ConsensoRegional | None = None,
    janela_seco_min: int | None = None,
    metropolitano: ConsensoMetropolitano | None = None,
) -> LinhaManifest:
    """Rotula um único frame, ou devolve a linha com o motivo da exclusão.

    A estação escolhida é a mais próxima, dentro do raio, que tenha ao menos uma
    leitura na janela. O desempate entre estações equidistantes é pelo id, para
    que a saída seja determinística.

    Args:
        frame: Metadados do frame.
        estacoes: Estações disponíveis, por id.
        series: Séries de leituras por id de estação.
        raio_max_km: Raio máximo aceito entre frame e estação.
        janela_min: Meia-largura da janela de agregação, em minutos.
        minutos_por_leitura: Duração do intervalo coberto por uma leitura.
        garoa_max: Limiar superior da classe `garoa`, em mm/h.
        moderada_max: Limiar superior da classe `moderada`, em mm/h.
        zona_morta_frac: Fração do limiar que define a zona morta.
        idade_maxima_posicao_s: Idade máxima aceita para a posição GPS do
            frame, em segundos (J8). Default sem limite (`inf`), só para não
            quebrar chamadas antigas/testes que não se importam com idade —
            `main()` sempre passa o valor configurado.
        consenso: Parâmetros do fallback por consenso regional, tentado só
            quando a estação próxima não deu leitura (fora do raio ou sem
            leitura na janela). None desliga o fallback.
        janela_seco_min: Meia-largura da janela da confirmação regional do
            `seco` (ver `seco_confirmado`), usando o raio do consenso — ou o
            próprio `raio_max_km` se o consenso estiver desligado. None
            desliga a confirmação.
        metropolitano: Parâmetros do `seco` sem GPS por consenso da rede toda
            (D1), aplicado só a frames sem posição e com timestamp. None
            desliga a regra (frame sem posição fica `sem_gps_fix`).

    Returns:
        A linha de manifest correspondente ao frame.
    """
    linha = LinhaManifest(
        arquivo=frame.arquivo,
        pasta=frame.pasta,
        evento_id=frame.evento_id,
        ts_utc=frame.ts.isoformat().replace("+00:00", "Z") if frame.ts else "",
        lat=frame.lat,
        lon=frame.lon,
        periodo=periodo_do_dia(frame.ts),
    )
    if frame.ts is None:
        linha.motivo_exclusao = MOTIVO_SEM_TIMESTAMP
        return linha
    if frame.lat is None or frame.lon is None:
        linha.motivo_exclusao = MOTIVO_SEM_FIX
        if metropolitano is not None:
            _rotular_seco_metropolitano(
                linha, frame, estacoes, series, metropolitano, minutos_por_leitura
            )
        return linha

    # Idade da posição (J8): registrada mesmo quando o frame acaba excluído
    # abaixo, para que quem ler o manifest depois saiba que aquele rótulo (ou
    # aquela exclusão) depende de uma posição inferida, e possa auditar ou
    # re-tunar `idade_maxima_posicao_s` sem precisar rodar o script de novo.
    linha.idade_posicao_s = frame.idade_posicao_s
    linha.origem_idade_posicao = frame.origem_idade_posicao
    if frame.idade_posicao_s is None or frame.idade_posicao_s > idade_maxima_posicao_s:
        # None = há coordenada mas nenhuma fonte permitiu estimar a idade dela
        # (schema 1 sem fix algum ainda observado na sessão) — mesmo motivo de
        # "sem fix utilizável" que já existia. Idade conhecida e grande demais
        # ganha um motivo próprio, distinto e auditável.
        linha.motivo_exclusao = (
            MOTIVO_POSICAO_DESATUALIZADA
            if frame.idade_posicao_s is not None
            else MOTIVO_SEM_FIX
        )
        return linha

    candidatas = []
    for est in estacoes.values():
        dist_km = haversine_km(frame.lat, frame.lon, est.lat, est.lon)
        if dist_km <= raio_max_km:
            candidatas.append((dist_km, est.estacao_id, est))
    candidatas.sort(key=lambda t: (t[0], t[1]))
    linha.n_estacoes_no_raio = len(candidatas)

    for dist_km, _, est in candidatas:
        mm_h, n_leituras, cobertura = intensidade_na_janela(
            series.get(est.estacao_id, []), frame.ts, janela_min, minutos_por_leitura
        )
        if mm_h is None:
            continue
        linha.estacao_id = est.estacao_id
        linha.estacao_nome = est.nome
        linha.dist_m = dist_km * 1000.0
        linha.mm_h = mm_h
        linha.n_leituras_janela = n_leituras
        linha.cobertura_min = cobertura
        linha.classe, linha.motivo_exclusao = classificar(
            mm_h, garoa_max, moderada_max, zona_morta_frac
        )
        if linha.classe == "seco" and janela_seco_min is not None:
            raio_seco = consenso.raio_km if consenso else raio_max_km
            if not seco_confirmado(
                frame, estacoes, series, raio_seco, janela_seco_min,
                minutos_por_leitura,
            ):
                linha.classe, linha.motivo_exclusao = "", MOTIVO_SECO_INCERTO
        if linha.classe:
            linha.metodo_rotulo = METODO_ESTACAO_PROXIMA
        return linha

    linha.motivo_exclusao = MOTIVO_SEM_LEITURA if candidatas else MOTIVO_FORA_DO_RAIO
    if consenso is not None:
        _rotular_por_consenso(
            linha, frame, estacoes, series, consenso, janela_min,
            minutos_por_leitura, garoa_max, moderada_max, zona_morta_frac,
            janela_seco_min,
        )
    return linha


def _rotular_por_consenso(
    linha: LinhaManifest,
    frame: Frame,
    estacoes: dict[str, Estacao],
    series: dict[str, list[tuple[datetime, float]]],
    consenso: ConsensoRegional,
    janela_min: int,
    minutos_por_leitura: int,
    garoa_max: float,
    moderada_max: float,
    zona_morta_frac: float,
    janela_seco_min: int | None = None,
) -> None:
    """Tenta rotular `linha` por consenso regional; altera a linha no lugar.

    Rotula só se houver pelo menos `consenso.min_estacoes` estações com leitura
    na janela dentro de `consenso.raio_km` e todas caírem na mesma classe, sem
    nenhuma na zona morta. O mm/h registrado é a mediana das estações e
    `dist_m` é a distância da estação MAIS LONGE usada — o pior caso, para que
    quem filtrar por distância não superestime a proximidade do rótulo. Em
    caso de falha, a linha fica sem classe e com o motivo correspondente.
    """
    assert frame.lat is not None and frame.lon is not None and frame.ts is not None
    leituras: list[tuple[str, float, float, int, int]] = []
    for est in sorted(estacoes.values(), key=lambda e: e.estacao_id):
        dist_km = haversine_km(frame.lat, frame.lon, est.lat, est.lon)
        if dist_km > consenso.raio_km:
            continue
        mm_h, n_leituras, cobertura = intensidade_na_janela(
            series.get(est.estacao_id, []), frame.ts, janela_min, minutos_por_leitura
        )
        if mm_h is not None:
            leituras.append((est.estacao_id, dist_km, mm_h, n_leituras, cobertura))

    if len(leituras) < consenso.min_estacoes:
        linha.motivo_exclusao = MOTIVO_POUCAS_ESTACOES
        return
    # Zero de báscula: a báscula registra em degraus de 0,2 mm, então a
    # 1,2 mm/h cai um tombo a cada 10 min e a janela de ±15 min pode ler zero
    # numa estação onde está garoando. Uma estação zerada na janela curta mas
    # com chuva em ±janela_seco_min não é evidência de seco (mesmo argumento da
    # confirmação regional do seco) — vira NEUTRA: não vota na classe. Só vale
    # para consenso em `garoa`: zero ao lado de moderada/forte continua
    # derrubando o consenso, porque aí a dúvida é de intensidade, não de báscula.
    neutras: set[str] = set()
    if consenso.zero_de_bascula_neutro and janela_seco_min is not None:
        for eid, _, mm_h, _, _ in leituras:
            if mm_h == 0.0:
                mm_h_largo, _, _ = intensidade_na_janela(
                    series.get(eid, []), frame.ts, janela_seco_min,
                    minutos_por_leitura,
                )
                if mm_h_largo:
                    neutras.add(eid)
        votantes = [li for li in leituras if li[0] not in neutras]
        classes_votantes = {
            classificar(mm_h, garoa_max, moderada_max, 0.0)[0]
            for _, _, mm_h, _, _ in votantes
        }
        if neutras and (len(votantes) < 2 or classes_votantes != {"garoa"}):
            neutras = set()
        leituras = [li for li in leituras if li[0] not in neutras]
    # Zona morta na mediana (D2): a zona morta existe para proteger o frame de
    # um valor que está na fronteira. Aplicada a cada estação, descartava campos
    # inteiros em que uma única leitura (2,4 mm/h) tocava a fronteira de 2,5
    # enquanto as demais diziam 1,2. Aqui cada estação é classificada sem zona
    # morta (exige-se só que todas caiam na mesma classe) e a zona morta é
    # aplicada uma vez, sobre a mediana — o valor que de fato vira o mm_h do
    # rótulo.
    zona_morta_estacao = 0.0 if consenso.zona_morta_na_mediana else zona_morta_frac
    classes = {
        classificar(mm_h, garoa_max, moderada_max, zona_morta_estacao)[0]
        for _, _, mm_h, _, _ in leituras
    }
    if len(classes) != 1 or "" in classes:
        linha.motivo_exclusao = MOTIVO_SEM_CONSENSO
        return
    if consenso.zona_morta_na_mediana:
        taxas_med = sorted(mm_h for _, _, mm_h, _, _ in leituras)
        m = len(taxas_med) // 2
        med = taxas_med[m] if len(taxas_med) % 2 else (taxas_med[m - 1] + taxas_med[m]) / 2
        if not classificar(med, garoa_max, moderada_max, zona_morta_frac)[0]:
            linha.motivo_exclusao = MOTIVO_SEM_CONSENSO
            return
    if classes == {"seco"} and janela_seco_min is not None and not seco_confirmado(
        frame, estacoes, series, consenso.raio_km, janela_seco_min,
        minutos_por_leitura,
    ):
        linha.motivo_exclusao = MOTIVO_SECO_INCERTO
        return

    taxas = sorted(mm_h for _, _, mm_h, _, _ in leituras)
    meio = len(taxas) // 2
    mediana = taxas[meio] if len(taxas) % 2 else (taxas[meio - 1] + taxas[meio]) / 2
    linha.classe = classes.pop()
    linha.motivo_exclusao = ""
    linha.metodo_rotulo = METODO_CONSENSO_REGIONAL
    linha.estacao_nome = "(consenso regional)"
    linha.estacoes_consenso = ";".join(eid for eid, *_ in leituras)
    if neutras:
        linha.estacoes_consenso += ";neutras:" + ",".join(sorted(neutras))
    linha.mm_h = mediana
    linha.dist_m = max(dist for _, dist, *_ in leituras) * 1000.0
    linha.n_leituras_janela = sum(n for *_, n, _ in leituras)
    linha.cobertura_min = min(c for *_, c in leituras)


def gerar_linhas(
    frames: list[Frame],
    estacoes: dict[str, Estacao],
    series: dict[str, list[tuple[datetime, float]]],
    cfg_rot: dict[str, Any],
    minutos_por_leitura: int,
    raio_max_km: float,
    idade_maxima_posicao_s: float,
    consenso: ConsensoRegional | None = None,
    janela_seco_min: int | None = None,
    metropolitano: ConsensoMetropolitano | None = None,
) -> list[LinhaManifest]:
    """Roda a rotulagem sobre todos os frames com um dado raio e idade máxima."""
    limiares = cfg_rot["limiares_mm_h"]
    return [
        rotular_frame(
            frame,
            estacoes,
            series,
            raio_max_km,
            int(cfg_rot["janela_min"]),
            minutos_por_leitura,
            float(limiares["garoa_max"]),
            float(limiares["moderada_max"]),
            float(cfg_rot["zona_morta_frac"]),
            idade_maxima_posicao_s,
            consenso,
            janela_seco_min,
            metropolitano,
        )
        for frame in frames
    ]


def montar_relatorio(
    linhas: list[LinhaManifest], jpg_sem_json: int, **meta: Any
) -> Relatorio:
    """Agrega as contagens do manifest num relatório auditável."""
    rel = Relatorio(total_frames=len(linhas), total_jpg_sem_json=jpg_sem_json, **meta)
    classes = Counter(li.classe for li in linhas if li.classe)
    motivos = Counter(li.motivo_exclusao for li in linhas if li.motivo_exclusao)
    rel.rotulados = sum(classes.values())
    rel.por_classe = {c: classes.get(c, 0) for c in CLASSES}
    rel.por_motivo = dict(sorted(motivos.items()))
    # Quantos rótulos (frames que ganharam classe) dependem de cada fonte de
    # idade da posição — é a rastreabilidade pedida pelo J8: sem isso, quem lê
    # o manifest não sabe quais rótulos vêm de um fix atual e quais dependem de
    # uma posição congelada (`ultimo_fix_em` ou inferida da sequência).
    rel.por_origem_idade_posicao = dict(
        sorted(
            Counter(
                li.origem_idade_posicao for li in linhas if li.classe
            ).items()
        )
    )
    rel.por_metodo_rotulo = dict(
        sorted(Counter(li.metodo_rotulo for li in linhas if li.classe).items())
    )
    rel.estacoes_usadas = dict(
        sorted(Counter(li.estacao_nome for li in linhas if li.classe).items())
    )
    por_evento: dict[str, dict[str, int]] = {}
    for li in linhas:
        alvo = por_evento.setdefault(li.evento_id, {"total": 0})
        alvo["total"] += 1
        chave = li.classe or li.motivo_exclusao
        alvo[chave] = alvo.get(chave, 0) + 1
    rel.por_evento = dict(sorted(por_evento.items()))
    seco_ev: dict[str, dict[str, int]] = {}
    for li in linhas:
        if li.classe == "seco":
            alvo = seco_ev.setdefault(li.evento_id, {})
            alvo[li.periodo] = alvo.get(li.periodo, 0) + 1
    rel.seco_por_evento_periodo = {
        ev: dict(sorted(d.items())) for ev, d in sorted(seco_ev.items())
    }
    return rel


def escrever_manifest(linhas: list[LinhaManifest], destino: Path) -> None:
    """Escreve o manifest em CSV, criando o diretório de destino se preciso."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(COLUNAS_MANIFEST))
        writer.writeheader()
        writer.writerows(li.to_row() for li in linhas)


def imprimir_resumo(rel: Relatorio, destino: Path, dry_run: bool) -> None:
    """Imprime o resumo da execução no terminal."""
    print(f"\nFrames com metadados: {rel.total_frames}")
    if rel.total_jpg_sem_json:
        print(f"Jpgs sem JSON par (fora do manifest): {rel.total_jpg_sem_json}")
    print(f"Rotulados: {rel.rotulados}  |  excluídos: "
          f"{rel.total_frames - rel.rotulados}")
    print("\nPor classe:")
    for classe in CLASSES:
        print(f"  {classe:<24}{rel.por_classe.get(classe, 0):>7}")
    print("\nPor motivo de exclusão:")
    for motivo, n in rel.por_motivo.items():
        print(f"  {motivo:<24}{n:>7}")
    if rel.seco_por_evento_periodo:
        print("\n`seco` por sessão e período:")
        for ev, por_per in rel.seco_por_evento_periodo.items():
            detalhe = "  ".join(f"{p or '?'}={n}" for p, n in por_per.items())
            print(f"  {ev:<36}{sum(por_per.values()):>6}   {detalhe}")
    if rel.ganho_zona_morta_mediana:
        print("\nGanho da zona morta na mediana (D2), por sessão:")
        for ev, d in rel.ganho_zona_morta_mediana.items():
            print(f"  {ev:<36}" + "  ".join(f"{c}={v:+d}" for c, v in d.items()))
    if rel.por_origem_idade_posicao:
        print("\nRótulos por origem da idade da posição:")
        for origem, n in rel.por_origem_idade_posicao.items():
            print(f"  {origem:<24}{n:>7}")
    if rel.por_metodo_rotulo:
        print("\nRótulos por método:")
        for metodo, n in rel.por_metodo_rotulo.items():
            print(f"  {metodo:<24}{n:>7}")
    if rel.estacoes_usadas:
        print("\nEstações que ancoraram rótulos:")
        for nome, n in rel.estacoes_usadas.items():
            print(f"  {nome:<24}{n:>7}")
    if rel.sensibilidade_raio:
        print("\nSensibilidade ao raio (frames rotulados):")
        cab = f"  {'raio':<10}" + "".join(f"{c:>10}" for c in CLASSES) + f"{'total':>10}"
        print(cab)
        for raio, contagem in rel.sensibilidade_raio.items():
            linha = f"  {raio:<10}" + "".join(
                f"{contagem.get(c, 0):>10}" for c in CLASSES
            )
            print(linha + f"{sum(contagem.get(c, 0) for c in CLASSES):>10}")
    if rel.sensibilidade_idade_posicao:
        print("\nSensibilidade à idade máxima da posição (frames rotulados):")
        cab = f"  {'idade':<10}" + "".join(f"{c:>10}" for c in CLASSES) + f"{'total':>10}"
        print(cab)
        for idade, contagem in rel.sensibilidade_idade_posicao.items():
            linha = f"  {idade:<10}" + "".join(
                f"{contagem.get(c, 0):>10}" for c in CLASSES
            )
            print(linha + f"{sum(contagem.get(c, 0) for c in CLASSES):>10}")
    print(f"\n{'[dry-run] manifest NÃO escrito' if dry_run else f'Manifest -> {destino}'}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Interpreta os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("ml/configs/rotulagem_imt.yaml"),
        help="Caminho do config YAML (ex.: ml/configs/rotulagem_imt.yaml).",
    )
    parser.add_argument(
        "--raio-km",
        type=float,
        default=None,
        help="Sobrescreve rotulagem.raio_max_km do config (em km).",
    )
    parser.add_argument(
        "--idade-maxima-posicao-s",
        type=float,
        default=None,
        help="Sobrescreve rotulagem.idade_maxima_posicao_s do config (em segundos).",
    )
    parser.add_argument(
        "--sem-consenso",
        action="store_true",
        help="Desliga o fallback por consenso regional (só estação próxima).",
    )
    parser.add_argument(
        "--sem-confirmacao-seco",
        action="store_true",
        help="Desliga a confirmação do seco em janela larga (regra antiga).",
    )
    parser.add_argument(
        "--sem-consenso-metropolitano",
        action="store_true",
        help="Desliga o `seco` sem GPS por consenso da rede (frames sem posição "
        "ficam sem_gps_fix).",
    )
    parser.add_argument(
        "--sem-zona-morta-mediana",
        action="store_true",
        help="Volta a aplicar a zona morta a cada estação do consenso regional "
        "(regra antiga), em vez de só sobre a mediana.",
    )
    parser.add_argument(
        "--janela-seco-min",
        type=int,
        default=None,
        help="Sobrescreve rotulagem.janela_seco_min do config (em minutos).",
    )
    parser.add_argument(
        "--sem-zero-de-bascula",
        action="store_true",
        help="Estação zerada com chuva recente volta a votar como seco no consenso.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcula e imprime o resumo sem escrever manifest nem relatório.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada do script.

    Returns:
        0 em caso de sucesso.
    """
    args = parse_args(argv)
    if not args.config.is_file():
        sys.exit(f"Config não encontrado: {args.config}")
    config, config_hash = load_config(args.config)

    cfg_rot = config["rotulagem"]
    minutos_por_leitura = int(config["leitura"]["minutos_por_leitura"])
    raio_max_km = (
        float(args.raio_km) if args.raio_km is not None
        else float(cfg_rot["raio_max_km"])
    )
    idade_maxima_posicao_s = (
        float(args.idade_maxima_posicao_s)
        if args.idade_maxima_posicao_s is not None
        else float(cfg_rot["idade_maxima_posicao_s"])
    )

    cfg_consenso = cfg_rot.get("consenso_regional") or {}
    consenso = (
        ConsensoRegional(
            raio_km=float(cfg_consenso["raio_km"]),
            min_estacoes=int(cfg_consenso["min_estacoes"]),
            zona_morta_na_mediana=(
                bool(cfg_consenso.get("zona_morta_na_mediana", False))
                and not args.sem_zona_morta_mediana
            ),
            zero_de_bascula_neutro=(
                bool(cfg_consenso.get("zero_de_bascula_neutro", False))
                and not args.sem_zero_de_bascula
            ),
        )
        if cfg_consenso.get("ativo") and not args.sem_consenso
        else None
    )

    cfg_metro = cfg_rot.get("consenso_metropolitano") or {}
    metropolitano = (
        ConsensoMetropolitano(
            min_estacoes=int(cfg_metro["min_estacoes"]),
            janela_min=int(cfg_metro["janela_min"]),
        )
        if cfg_metro.get("ativo") and not args.sem_consenso_metropolitano
        else None
    )

    if args.sem_confirmacao_seco:
        janela_seco_min = None
    elif args.janela_seco_min is not None:
        janela_seco_min = args.janela_seco_min
    else:
        cfg_seco = cfg_rot.get("janela_seco_min")
        janela_seco_min = None if cfg_seco is None else int(cfg_seco)

    estacoes, series = carregar_leituras(Path(config["leituras_csv"]))
    frames, jpg_sem_json = carregar_frames(Path(config["raiz_frames"]))
    print(f"Estações com leituras: {len(estacoes)}  |  frames: {len(frames)}")

    linhas = gerar_linhas(
        frames,
        estacoes,
        series,
        cfg_rot,
        minutos_por_leitura,
        raio_max_km,
        idade_maxima_posicao_s,
        consenso,
        janela_seco_min,
        metropolitano,
    )
    rel = montar_relatorio(
        linhas,
        jpg_sem_json,
        config_sha256=config_hash,
        timestamp_execucao_utc=datetime.now(timezone.utc).isoformat(),
        raio_max_km=raio_max_km,
        janela_min=int(cfg_rot["janela_min"]),
        zona_morta_frac=float(cfg_rot["zona_morta_frac"]),
        minutos_por_leitura=minutos_por_leitura,
        idade_maxima_posicao_s=idade_maxima_posicao_s,
        consenso_raio_km=consenso.raio_km if consenso else None,
        consenso_min_estacoes=consenso.min_estacoes if consenso else None,
        janela_seco_min=janela_seco_min,
        consenso_zona_morta_na_mediana=(
            consenso.zona_morta_na_mediana if consenso else None
        ),
        consenso_metropolitano_min_estacoes=(
            metropolitano.min_estacoes if metropolitano else None
        ),
        consenso_metropolitano_janela_min=(
            metropolitano.janela_min if metropolitano else None
        ),
    )

    if consenso is not None and consenso.zona_morta_na_mediana:
        # Ganho da regra D2: mesma rodada, só com a zona morta voltando a ser
        # por estação. Diferença = frames que a regra nova resgatou.
        antiga = gerar_linhas(
            frames, estacoes, series, cfg_rot, minutos_por_leitura, raio_max_km,
            idade_maxima_posicao_s,
            ConsensoRegional(consenso.raio_km, consenso.min_estacoes, False),
            janela_seco_min, metropolitano,
        )
        antes = Counter((li.evento_id, li.classe) for li in antiga if li.classe)
        depois = Counter((li.evento_id, li.classe) for li in linhas if li.classe)
        ganho: dict[str, dict[str, int]] = {}
        for (ev, cl) in sorted(set(antes) | set(depois)):
            delta = depois.get((ev, cl), 0) - antes.get((ev, cl), 0)
            if delta:
                ganho.setdefault(ev, {})[cl] = delta
        rel.ganho_zona_morta_mediana = ganho

    for raio in config.get("sensibilidade_raio_km", []):
        alt = gerar_linhas(
            frames,
            estacoes,
            series,
            cfg_rot,
            minutos_por_leitura,
            float(raio),
            idade_maxima_posicao_s,
            consenso,
            janela_seco_min,
            metropolitano,
        )
        contagem = Counter(li.classe for li in alt if li.classe)
        rel.sensibilidade_raio[f"{float(raio):.1f} km"] = {
            c: contagem.get(c, 0) for c in CLASSES
        }

    for idade in config.get("sensibilidade_idade_maxima_s", []):
        alt = gerar_linhas(
            frames,
            estacoes,
            series,
            cfg_rot,
            minutos_por_leitura,
            raio_max_km,
            float(idade),
            consenso,
            janela_seco_min,
            metropolitano,
        )
        contagem = Counter(li.classe for li in alt if li.classe)
        rel.sensibilidade_idade_posicao[f"{float(idade):.0f} s"] = {
            c: contagem.get(c, 0) for c in CLASSES
        }

    destino = Path(config["saida_manifest"])
    if not args.dry_run:
        escrever_manifest(linhas, destino)
        relatorio_path = Path(config["saida_relatorio"])
        relatorio_path.parent.mkdir(parents=True, exist_ok=True)
        relatorio_path.write_text(
            json.dumps(rel.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    imprimir_resumo(rel, destino, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
