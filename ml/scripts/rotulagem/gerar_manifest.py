#!/usr/bin/env python3
"""Gera o manifest de rotulagem frame -> classe de chuva (F1.3 do plano de dataset).

Para cada frame da coleta própria que tenha GPS fix, procura a estação
pluviométrica mais próxima dentro do raio configurado, agrega a janela de tempo
centrada no instante da captura, converte para mm/h e aplica os limiares do
plano (`seco`, `garoa`, `moderada`, `forte`) com zona morta nas fronteiras.

Todo frame com metadados entra no manifest: os que não puderam ser rotulados
saem com a coluna `motivo_exclusao` preenchida, nunca são omitidos em silêncio.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

# `distancia.py` mora no diretório irmão `estacoes/`. A árvore `ml/scripts/` não
# é um pacote instalável, então o caminho é injetado explicitamente em vez de
# duplicar a implementação de haversine aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estacoes"))

from distancia import haversine_km  # noqa: E402

CLASSES = ("seco", "garoa", "moderada", "forte")

MOTIVO_SEM_TIMESTAMP = "sem_timestamp"
MOTIVO_SEM_FIX = "sem_gps_fix"
MOTIVO_FORA_DO_RAIO = "sem_estacao_no_raio"
MOTIVO_SEM_LEITURA = "sem_leitura_na_janela"
MOTIVO_ZONA_MORTA = "zona_morta"

COLUNAS_MANIFEST = (
    "arquivo",
    "pasta",
    "evento_id",
    "ts_utc",
    "lat",
    "lon",
    "estacao_id",
    "estacao_nome",
    "dist_m",
    "mm_h",
    "classe",
    "n_leituras_janela",
    "cobertura_min",
    "n_estacoes_no_raio",
    "motivo_exclusao",
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
        lat: Latitude do GPS; None se não houve fix.
        lon: Longitude do GPS; None se não houve fix.
    """

    arquivo: str
    pasta: str
    ts: datetime | None
    lat: float | None
    lon: float | None

    @property
    def evento_id(self) -> str:
        """Identificador do evento de coleta (pasta + dia), para split por evento."""
        dia = self.ts.date().isoformat() if self.ts else "sem_data"
        return f"{self.pasta}__{dia}"


@dataclass
class LinhaManifest:
    """Uma linha do manifest: um frame, rotulado ou com motivo de exclusão."""

    arquivo: str
    pasta: str
    evento_id: str
    ts_utc: str
    lat: float | None
    lon: float | None
    estacao_id: str = ""
    estacao_nome: str = ""
    dist_m: float | None = None
    mm_h: float | None = None
    classe: str = ""
    n_leituras_janela: int = 0
    cobertura_min: int = 0
    n_estacoes_no_raio: int = 0
    motivo_exclusao: str = ""

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
            "estacao_id": self.estacao_id,
            "estacao_nome": self.estacao_nome,
            "dist_m": "" if self.dist_m is None else f"{self.dist_m:.1f}",
            "mm_h": "" if self.mm_h is None else f"{self.mm_h:.4f}",
            "classe": self.classe,
            "n_leituras_janela": self.n_leituras_janela,
            "cobertura_min": self.cobertura_min,
            "n_estacoes_no_raio": self.n_estacoes_no_raio,
            "motivo_exclusao": self.motivo_exclusao,
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
    total_frames: int = 0
    total_jpg_sem_json: int = 0
    rotulados: int = 0
    por_classe: dict[str, int] = field(default_factory=dict)
    por_motivo: dict[str, int] = field(default_factory=dict)
    por_evento: dict[str, dict[str, int]] = field(default_factory=dict)
    estacoes_usadas: dict[str, int] = field(default_factory=dict)
    sensibilidade_raio: dict[str, dict[str, int]] = field(default_factory=dict)

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
            },
            "total_frames": self.total_frames,
            "total_jpg_sem_json": self.total_jpg_sem_json,
            "rotulados": self.rotulados,
            "por_classe": self.por_classe,
            "por_motivo": self.por_motivo,
            "por_evento": self.por_evento,
            "estacoes_usadas": self.estacoes_usadas,
            "sensibilidade_raio": self.sensibilidade_raio,
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
            tem_fix = bool(gps.get("fix")) and gps.get("latitude") is not None
            frames.append(
                Frame(
                    arquivo=meta.get("arquivo", f"{caminho.stem}.jpg"),
                    pasta=pasta_dir.name,
                    ts=_parse_ts(str(meta.get("capturado_em_utc", ""))),
                    lat=float(gps["latitude"]) if tem_fix else None,
                    lon=float(gps["longitude"]) if tem_fix else None,
                )
            )
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
    )
    if frame.ts is None:
        linha.motivo_exclusao = MOTIVO_SEM_TIMESTAMP
        return linha
    if frame.lat is None or frame.lon is None:
        linha.motivo_exclusao = MOTIVO_SEM_FIX
        return linha

    candidatas = []
    for est in estacoes.values():
        dist_km = haversine_km(frame.lat, frame.lon, est.lat, est.lon)
        if dist_km <= raio_max_km:
            candidatas.append((dist_km, est.estacao_id, est))
    candidatas.sort(key=lambda t: (t[0], t[1]))
    linha.n_estacoes_no_raio = len(candidatas)
    if not candidatas:
        linha.motivo_exclusao = MOTIVO_FORA_DO_RAIO
        return linha

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
        return linha

    linha.motivo_exclusao = MOTIVO_SEM_LEITURA
    return linha


def gerar_linhas(
    frames: list[Frame],
    estacoes: dict[str, Estacao],
    series: dict[str, list[tuple[datetime, float]]],
    cfg_rot: dict[str, Any],
    minutos_por_leitura: int,
    raio_max_km: float,
) -> list[LinhaManifest]:
    """Roda a rotulagem sobre todos os frames com um dado raio."""
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

    estacoes, series = carregar_leituras(Path(config["leituras_csv"]))
    frames, jpg_sem_json = carregar_frames(Path(config["raiz_frames"]))
    print(f"Estações com leituras: {len(estacoes)}  |  frames: {len(frames)}")

    linhas = gerar_linhas(
        frames, estacoes, series, cfg_rot, minutos_por_leitura, raio_max_km
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
    )

    for raio in config.get("sensibilidade_raio_km", []):
        alt = gerar_linhas(
            frames, estacoes, series, cfg_rot, minutos_por_leitura, float(raio)
        )
        contagem = Counter(li.classe for li in alt if li.classe)
        rel.sensibilidade_raio[f"{float(raio):.1f} km"] = {
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
