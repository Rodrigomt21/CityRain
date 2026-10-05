#!/usr/bin/env python3
"""Normaliza a orientação da coleta própria de frames (câmera veicular na Jetson Nano).

A câmera foi montada de ponta-cabeça em três das quatro sessões de coleta,
então três pastas precisam de rotação de 180° para que o capô/painel do
carro fique embaixo e o céu em cima (orientação correta de dashcam). Uma
pasta já está correta e não deve ser tocada.

Este script materializa `ml/data/raw/imt_coleta/<pasta>/` em
`ml/data/processed/imt_coleta/<pasta>/`, aplicando a rotação declarada em um
config YAML, copiando os metadados `.json` correspondentes, pulando lixo
(jpg de 0 byte, json órfão, jpg órfão) e gravando um relatório auditável por
pasta. Nunca escreve em `raiz_entrada`.

Ver docs/specs/spec-normalizacao-orientacao.md para a especificação completa.

Exemplo de uso:
    python ml/scripts/preprocessamento/normalizar_orientacao.py \\
        --config ml/configs/normalizacao_imt.yaml [--dry-run] [--force] [--amostras 4]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

JPEG_QUALITY = 95
JUNK_NAMES = {".DS_Store", "Thumbs.db"}


@dataclass
class SkipRecord:
    """Registro de um arquivo pulado durante a normalização.

    Attributes:
        arquivo: Nome do arquivo pulado (sem caminho).
        motivo: Um de `zero_byte`, `json_orfao`, `jpg_orfao`.
    """

    arquivo: str
    motivo: str

    def to_dict(self) -> dict[str, str]:
        """Converte o registro em dicionário serializável em JSON."""
        return {"arquivo": self.arquivo, "motivo": self.motivo}


@dataclass
class PastaReport:
    """Relatório de execução da normalização de uma pasta.

    Attributes:
        pasta: Nome da pasta processada.
        rotacao_aplicada: Rotação em graus aplicada (0 ou 180).
        total_entrada: Total de jpgs encontrados na origem (inclui 0-byte).
        total_json_entrada: Total de jsons encontrados na origem.
        total_saida: Total de jpgs presentes na saída ao final da execução.
        total_json_saida: Total de jsons presentes na saída ao final da execução.
        pulados: Lista de arquivos pulados com motivo.
        ja_existia: Quantidade de pares que já existiam na saída (não reescritos).
        processados: Quantidade de pares efetivamente escritos nesta execução.
        timestamp_execucao_utc: Timestamp ISO 8601 UTC do fim do processamento.
        config_sha256: Hash sha256 do arquivo de config usado.
        dry_run: Se a execução foi em modo dry-run (nada foi escrito).
    """

    pasta: str
    rotacao_aplicada: int
    total_entrada: int = 0
    total_json_entrada: int = 0
    total_saida: int = 0
    total_json_saida: int = 0
    pulados: list[SkipRecord] = field(default_factory=list)
    ja_existia: int = 0
    processados: int = 0
    timestamp_execucao_utc: str = ""
    config_sha256: str = ""
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Converte o relatório em dicionário serializável em JSON."""
        return {
            "pasta": self.pasta,
            "rotacao_aplicada": self.rotacao_aplicada,
            "total_entrada": self.total_entrada,
            "total_json_entrada": self.total_json_entrada,
            "total_saida": self.total_saida,
            "total_json_saida": self.total_json_saida,
            "pulados": [p.to_dict() for p in self.pulados],
            "ja_existia": self.ja_existia,
            "processados": self.processados,
            "timestamp_execucao_utc": self.timestamp_execucao_utc,
            "config_sha256": self.config_sha256,
            "dry_run": self.dry_run,
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
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(config_path: Path) -> tuple[dict[str, Any], str]:
    """Carrega o config YAML de normalização.

    Args:
        config_path: Caminho para o arquivo YAML de config.

    Returns:
        Tupla (config carregado como dict, sha256 do arquivo de config).
    """
    config_hash = sha256_of_file(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config, config_hash


def assert_not_inside(path: Path, forbidden_root: Path) -> None:
    """Garante que `path` não está dentro de `forbidden_root`.

    Usado para impedir que o script escreva acidentalmente em `raiz_entrada`.

    Args:
        path: Caminho a verificar.
        forbidden_root: Raiz proibida.

    Raises:
        RuntimeError: Se `path` resolver para dentro de `forbidden_root`.
    """
    resolved_path = path.resolve()
    resolved_forbidden = forbidden_root.resolve()
    if resolved_path == resolved_forbidden or resolved_forbidden in resolved_path.parents:
        raise RuntimeError(
            f"Abortando: caminho de escrita '{resolved_path}' cai dentro de "
            f"raiz_entrada '{resolved_forbidden}'. O script nunca escreve em raw/."
        )


def list_jpgs(directory: Path) -> list[Path]:
    """Lista arquivos .jpg diretamente sob `directory` (não recursivo), ignorando lixo.

    Args:
        directory: Diretório a listar.

    Returns:
        Lista ordenada de caminhos .jpg.
    """
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() == ".jpg" and p.name not in JUNK_NAMES
    )


def list_jsons(directory: Path) -> list[Path]:
    """Lista arquivos .json diretamente sob `directory` (não recursivo), ignorando lixo.

    Args:
        directory: Diretório a listar.

    Returns:
        Lista ordenada de caminhos .json.
    """
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() == ".json" and p.name not in JUNK_NAMES
    )


def discover_pasta_warnings(raiz_entrada: Path, pastas_config: dict[str, Any]) -> list[str]:
    """Compara pastas presentes no disco com as declaradas no config.

    Args:
        raiz_entrada: Diretório raiz de entrada.
        pastas_config: Mapeamento pasta -> config, do YAML.

    Returns:
        Lista de mensagens de warning (pasta no disco sem config ou vice-versa).
    """
    warnings: list[str] = []
    if not raiz_entrada.is_dir():
        warnings.append(f"AVISO: raiz_entrada '{raiz_entrada}' não existe no disco.")
        return warnings

    pastas_disco = {p.name for p in raiz_entrada.iterdir() if p.is_dir()}
    pastas_cfg = set(pastas_config.keys())

    for extra in sorted(pastas_disco - pastas_cfg):
        warnings.append(
            f"AVISO: pasta '{extra}' existe em '{raiz_entrada}' mas não está no config "
            f"— não será processada."
        )
    for faltante in sorted(pastas_cfg - pastas_disco):
        warnings.append(
            f"AVISO: pasta '{faltante}' está no config mas não existe em '{raiz_entrada}'."
        )
    return warnings


def process_pasta(
    nome: str,
    cfg_entry: dict[str, Any],
    raiz_entrada: Path,
    raiz_saida: Path,
    config_hash: str,
    dry_run: bool,
    force: bool,
) -> PastaReport:
    """Processa uma pasta: rotaciona jpgs, copia jsons, pula lixo, gera relatório.

    Args:
        nome: Nome da pasta (subdiretório de raiz_entrada e raiz_saida).
        cfg_entry: Entrada de config para a pasta (rotacao_graus, subpasta_jpgs opcional).
        raiz_entrada: Diretório raiz de entrada (nunca escrito).
        raiz_saida: Diretório raiz de saída.
        config_hash: Hash sha256 do arquivo de config usado nesta execução.
        dry_run: Se True, não escreve nada — apenas conta o que faria.
        force: Se True, reprocessa mesmo que o arquivo de saída já exista.

    Returns:
        Relatório de execução da pasta.
    """
    rotacao = int(cfg_entry.get("rotacao_graus", 0))
    subpasta_jpgs = cfg_entry.get("subpasta_jpgs")

    pasta_entrada = raiz_entrada / nome
    jpg_source_dir = pasta_entrada / subpasta_jpgs if subpasta_jpgs else pasta_entrada
    json_source_dir = pasta_entrada  # metadados sempre na raiz da pasta, nunca na subpasta

    pasta_saida = raiz_saida / nome
    if not dry_run:
        assert_not_inside(pasta_saida, raiz_entrada)
        pasta_saida.mkdir(parents=True, exist_ok=True)

    report = PastaReport(
        pasta=nome,
        rotacao_aplicada=rotacao,
        config_sha256=config_hash,
        dry_run=dry_run,
    )

    jpgs = list_jpgs(jpg_source_dir)
    jsons = list_jsons(json_source_dir)
    report.total_entrada = len(jpgs)
    report.total_json_entrada = len(jsons)

    json_stems = {p.stem for p in jsons}
    json_by_stem = {p.stem: p for p in jsons}

    valid_jpgs: list[Path] = []
    nonzero_jpg_stems: set[str] = set()
    for jpg in jpgs:
        if jpg.stat().st_size == 0:
            report.pulados.append(SkipRecord(arquivo=jpg.name, motivo="zero_byte"))
            continue
        valid_jpgs.append(jpg)
        nonzero_jpg_stems.add(jpg.stem)

    has_metadata = len(jsons) > 0

    if has_metadata:
        # jpg órfão: jpg válido sem json correspondente.
        for jpg in valid_jpgs:
            if jpg.stem not in json_stems:
                report.pulados.append(SkipRecord(arquivo=jpg.name, motivo="jpg_orfao"))
        # json órfão: json sem jpg válido correspondente.
        for stem, json_path in sorted(json_by_stem.items()):
            if stem not in nonzero_jpg_stems:
                report.pulados.append(SkipRecord(arquivo=json_path.name, motivo="json_orfao"))

        pares = [
            (jpg, json_by_stem[jpg.stem])
            for jpg in valid_jpgs
            if jpg.stem in json_stems
        ]
    else:
        pares = [(jpg, None) for jpg in valid_jpgs]

    for jpg_path, json_path in pares:
        jpg_dest = pasta_saida / jpg_path.name
        json_dest = pasta_saida / json_path.name if json_path is not None else None

        jpg_exists = jpg_dest.exists()
        json_exists = json_dest.exists() if json_dest is not None else True
        already_done = jpg_exists and json_exists

        if dry_run:
            if already_done and not force:
                report.ja_existia += 1
            else:
                report.processados += 1
            continue

        if already_done and not force:
            report.ja_existia += 1
        else:
            assert_not_inside(jpg_dest, raiz_entrada)
            _write_jpg(jpg_path, jpg_dest, rotacao)
            if json_path is not None and json_dest is not None:
                assert_not_inside(json_dest, raiz_entrada)
                shutil.copy2(json_path, json_dest)
            report.processados += 1

    if dry_run:
        report.total_saida = report.ja_existia + report.processados
        report.total_json_saida = report.total_saida if has_metadata else 0
    else:
        report.total_saida = len(list_jpgs(pasta_saida))
        report.total_json_saida = len(list_jsons(pasta_saida))

    report.timestamp_execucao_utc = datetime.now(timezone.utc).isoformat()
    return report


def _write_jpg(src: Path, dest: Path, rotacao: int) -> None:
    """Escreve o jpg de saída aplicando a rotação declarada.

    Rotação de 180° é feita via `Image.transpose` (exata, sem interpolação) e
    salva com `quality=95`. Rotação 0° é uma cópia byte a byte (`shutil.copy2`),
    sem reencodar.

    Args:
        src: Caminho do jpg de origem.
        dest: Caminho do jpg de destino.
        rotacao: Rotação em graus (0 ou 180).
    """
    if rotacao == 0:
        shutil.copy2(src, dest)
        return
    if rotacao == 180:
        with Image.open(src) as im:
            rotated = im.transpose(Image.Transpose.ROTATE_180)
            rotated.save(dest, format="JPEG", quality=JPEG_QUALITY)
        return
    raise ValueError(f"Rotação não suportada: {rotacao}° (apenas 0 ou 180 são suportados).")


def write_pasta_report(report: PastaReport, raiz_saida: Path) -> None:
    """Grava o relatório `_normalizacao.json` da pasta em disco.

    Args:
        report: Relatório da pasta.
        raiz_saida: Diretório raiz de saída.
    """
    import json

    pasta_saida = raiz_saida / report.pasta
    pasta_saida.mkdir(parents=True, exist_ok=True)
    report_path = pasta_saida / "_normalizacao.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)


def print_summary(reports: list[PastaReport], dry_run: bool) -> None:
    """Imprime um resumo tabular da execução no stdout.

    Args:
        reports: Lista de relatórios por pasta.
        dry_run: Se a execução foi em modo dry-run.
    """
    header = (
        f"{'pasta':<22} {'rot':>4} {'entrada':>8} {'saida':>8} "
        f"{'pulados':>8} {'ja_existia':>11} {'processados':>12}"
    )
    print()
    print("=== Resumo da normalização" + (" (DRY-RUN)" if dry_run else "") + " ===")
    print(header)
    print("-" * len(header))
    for r in reports:
        print(
            f"{r.pasta:<22} {r.rotacao_aplicada:>4} {r.total_entrada:>8} {r.total_saida:>8} "
            f"{len(r.pulados):>8} {r.ja_existia:>11} {r.processados:>12}"
        )
    print()
    for r in reports:
        for skip in r.pulados:
            print(f"  [{r.pasta}] pulado: {skip.arquivo} (motivo={skip.motivo})")


def _percentile_index(length: int, percentile: float) -> int:
    """Calcula o índice de lista correspondente a um percentil.

    Args:
        length: Tamanho da lista.
        percentile: Percentil desejado (0-100).

    Returns:
        Índice (0-based) clampado nos limites da lista.
    """
    if length <= 1:
        return 0
    idx = int(round((percentile / 100.0) * (length - 1)))
    return max(0, min(length - 1, idx))


def _percentiles_for_n(n: int) -> list[float]:
    """Gera N percentis espalhados entre 10 e 85 (default do RF7: 10/35/60/85 p/ N=4).

    Args:
        n: Quantidade de amostras desejada.

    Returns:
        Lista de N percentis.
    """
    if n <= 0:
        return []
    if n == 1:
        return [50.0]
    step = (85.0 - 10.0) / (n - 1)
    return [10.0 + i * step for i in range(n)]


def generate_amostras(raiz_saida: Path, pastas: list[str], n: int) -> None:
    """Gera grids de amostras para conferência visual, uma por pasta.

    Args:
        raiz_saida: Diretório raiz de saída (já processado).
        pastas: Nomes das pastas a amostrar.
        n: Quantidade de frames por grid (default 4, percentis 10/35/60/85).
    """
    amostras_dir = raiz_saida / "_amostras"
    amostras_dir.mkdir(parents=True, exist_ok=True)

    percentis = _percentiles_for_n(n)

    for pasta in pastas:
        pasta_dir = raiz_saida / pasta
        jpgs = list_jpgs(pasta_dir)
        if not jpgs:
            print(f"  [amostras] pasta '{pasta}' sem jpgs na saída — pulando grid.")
            continue

        indices = sorted({_percentile_index(len(jpgs), p) for p in percentis})
        escolhidos = [jpgs[i] for i in indices]

        tile_w, tile_h = 640, 480
        cols = max(1, round(len(escolhidos) ** 0.5))
        rows = (len(escolhidos) + cols - 1) // cols
        grid = Image.new("RGB", (tile_w * cols, tile_h * rows), color=(0, 0, 0))

        for i, jpg_path in enumerate(escolhidos):
            with Image.open(jpg_path) as im:
                im = im.convert("RGB")
                if im.size != (tile_w, tile_h):
                    im = im.resize((tile_w, tile_h))
                col, row = i % cols, i // cols
                grid.paste(im, (col * tile_w, row * tile_h))

        grid_path = amostras_dir / f"{pasta}.jpg"
        grid.save(grid_path, format="JPEG", quality=JPEG_QUALITY)
        print(f"  [amostras] {pasta}: grid com {len(escolhidos)} frame(s) -> {grid_path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Faz o parsing dos argumentos de linha de comando.

    Args:
        argv: Lista de argumentos (default: sys.argv[1:]).

    Returns:
        Namespace com os argumentos parseados.
    """
    parser = argparse.ArgumentParser(
        description="Normaliza a orientação da coleta própria de frames (CityRain)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Caminho do config YAML (ex.: ml/configs/normalizacao_imt.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista o que faria (contagens por pasta e motivo) sem escrever nada.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocessa mesmo que o arquivo de saída já exista.",
    )
    parser.add_argument(
        "--amostras",
        type=int,
        default=4,
        help="Quantidade de frames por grid de amostras (default: 4). Use 0 para desativar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada do script.

    Args:
        argv: Lista de argumentos (default: sys.argv[1:]).

    Returns:
        Código de saída do processo (0 = sucesso).
    """
    args = parse_args(argv)

    config, config_hash = load_config(args.config)
    raiz_entrada = Path(config["raiz_entrada"])
    raiz_saida = Path(config["raiz_saida"])
    pastas_config = config.get("pastas", {})

    if not args.dry_run:
        assert_not_inside(raiz_saida, raiz_entrada)

    warnings = discover_pasta_warnings(raiz_entrada, pastas_config)
    for w in warnings:
        print(w, file=sys.stderr)

    reports: list[PastaReport] = []
    for nome, cfg_entry in pastas_config.items():
        pasta_entrada = raiz_entrada / nome
        if not pasta_entrada.is_dir():
            continue  # já reportado como warning acima
        report = process_pasta(
            nome=nome,
            cfg_entry=cfg_entry,
            raiz_entrada=raiz_entrada,
            raiz_saida=raiz_saida,
            config_hash=config_hash,
            dry_run=args.dry_run,
            force=args.force,
        )
        reports.append(report)
        if not args.dry_run:
            write_pasta_report(report, raiz_saida)

    print_summary(reports, dry_run=args.dry_run)

    if not args.dry_run and args.amostras > 0:
        generate_amostras(raiz_saida, [r.pasta for r in reports], args.amostras)
    elif args.dry_run:
        print("(dry-run: amostras não geradas)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
