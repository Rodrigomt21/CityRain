#!/usr/bin/env python3
"""Create a small, deterministic visual review batch from image sources.

Brightness and contrast are review cues only. This script never infers labels,
rain intensity, or modifies source files.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageStat
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("Pillow is required. Use an interpreter that already has Pillow installed.") from exc


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PATH_HEADERS = ("path", "image_path", "filepath", "file_path", "relative_path", "caminho", "arquivo", "imagem")
SOURCE_HEADERS = ("source", "source_id", "origin", "origem", "origin_folder", "dataset", "folder", "pasta")


def parse_root(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("root must be NAME=PATH")
    name, path = value.split("=", 1)
    if not name.strip() or not path.strip():
        raise argparse.ArgumentTypeError("root must be NAME=PATH")
    return name.strip(), Path(path).expanduser()


def header_name(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    by_lower = {key.strip().lower(): key for key in row}
    return next((by_lower[name] for name in candidates if name in by_lower), None)


def images_under(root: Path) -> list[Path]:
    if root.is_file():
        return [root.resolve()] if root.suffix.lower() in IMAGE_SUFFIXES else []
    if not root.is_dir():
        return []
    return sorted((p.resolve() for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES), key=lambda p: str(p).casefold())


def inventory_groups(csv_path: Path, path_column: str | None, source_column: str | None,
                     include_derived: bool = False) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    records: list[tuple[str, Path, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("inventory CSV has no header")
        first = {key: "" for key in reader.fieldnames}
        path_key = path_column or header_name(first, PATH_HEADERS)
        source_key = source_column or header_name(first, SOURCE_HEADERS)
        role_key = header_name(first, ("role",))
        zero_key = header_name(first, ("zero_bytes",))
        hash_key = header_name(first, ("sha256", "hash"))
        if path_key not in reader.fieldnames:
            raise ValueError(f"path column not found; headers: {', '.join(reader.fieldnames)}")
        if source_key and source_key not in reader.fieldnames:
            raise ValueError(f"source column {source_key!r} not found")
        base = csv_path.parent
        for row in reader:
            accepted_roles = {"", "photo", "image", "frame"}
            if include_derived:
                accepted_roles.add("derived")
            if role_key and (row.get(role_key) or "").strip().lower() not in accepted_roles:
                continue
            if zero_key and (row.get(zero_key) or "").strip().lower() in {"1", "true", "yes", "sim"}:
                continue
            digest = (row.get(hash_key) or "").strip().lower() if hash_key else ""
            raw = (row.get(path_key) or "").strip()
            if not raw:
                continue
            p = Path(raw).expanduser()
            if not p.is_absolute():
                cwd_candidate = Path.cwd() / p
                p = cwd_candidate if cwd_candidate.exists() else base / p
            label = (row.get(source_key) or "").strip() if source_key else ""
            if not label:
                label = p.parent.name or "sem_origem"
            # A file at the inventory root has no dataset provenance and is likely
            # a project artifact rather than a collection source.
            if label in {".", "./"}:
                continue
            if p.is_dir():
                records.extend((label, image, "") for image in images_under(p))
            elif p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
                records.append((label, p.resolve(), digest))
    # Lexical-first canonical path for exact hash duplicates, independent of CSV order.
    seen_hashes: set[str] = set()
    for label, path, digest in sorted(records, key=lambda item: str(item[1]).casefold()):
        if digest and digest in seen_hashes:
            continue
        if digest:
            seen_hashes.add(digest)
        groups[label].append(path)
    return {name: sorted(set(paths), key=lambda p: str(p).casefold()) for name, paths in groups.items()}


def evenly_spaced(items: list[Path], count: int, rng: random.Random) -> list[Path]:
    """Choose positions across the sorted source to reduce temporal clustering."""
    if len(items) <= count:
        return items
    # A seeded phase makes repeated runs stable while avoiding always taking endpoints.
    phase = rng.random()
    positions = [min(len(items) - 1, int((i + phase) * len(items) / count)) for i in range(count)]
    return [items[i] for i in positions]


def image_cues(path: Path) -> tuple[Image.Image, float, float]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((240, 150), Image.Resampling.LANCZOS)
        stats = ImageStat.Stat(image.convert("L"))
        return image.copy(), float(stats.mean[0]), float(stats.stddev[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-csv", type=Path, help="Inventory CSV containing image paths")
    parser.add_argument("--path-column", help="Inventory path column (auto-detected by default)")
    parser.add_argument("--source-column", help="Inventory source column (auto-detected by default)")
    parser.add_argument("--include-derived", action="store_true", help="Include processed/derived images from inventory")
    parser.add_argument("--root", action="append", type=parse_root, default=[], metavar="NAME=PATH", help="Image directory; repeat for each source")
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/cityrain-triagem"))
    parser.add_argument("--per-source", type=int, default=20, help="Maximum sampled images from each source (default: 20)")
    parser.add_argument("--max-images", type=int, default=160, help="Overall sample cap (default: 160)")
    parser.add_argument("--sheet-size", type=int, default=30, help="Images per contact sheet")
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--overwrite", action="store_true", help="Allow writing into an output directory containing files")
    args = parser.parse_args()
    if args.per_source < 1 or args.max_images < 1 or args.sheet_size < 1:
        parser.error("sample and sheet limits must be positive")
    if bool(args.inventory_csv) == bool(args.root):
        parser.error("provide exactly one of --inventory-csv or one or more --root NAME=PATH")

    if args.inventory_csv:
        groups = inventory_groups(args.inventory_csv.expanduser().resolve(), args.path_column, args.source_column, args.include_derived)
    else:
        groups = {name: images_under(path.expanduser().resolve()) for name, path in args.root}
    groups = {name: paths for name, paths in sorted(groups.items()) if paths}
    if not groups:
        parser.error("no readable image files found")

    rng = random.Random(args.seed)
    selected: list[tuple[str, Path]] = []
    # Start with the per-source cap, then trim the largest quotas to meet the
    # global maximum. Sources stay represented while the cap allows it.
    quotas = {name: min(args.per_source, len(paths)) for name, paths in groups.items()}
    while sum(quotas.values()) > args.max_images:
        largest = max(quotas, key=lambda n: (quotas[n], n))
        if quotas[largest] <= 0:
            break
        quotas[largest] -= 1
    for name, paths in groups.items():
        selected.extend((name, path) for path in evenly_spaced(paths, quotas[name], rng))

    args.output.expanduser().mkdir(parents=True, exist_ok=True)
    output = args.output.expanduser().resolve()
    existing = list(output.iterdir())
    if existing and not args.overwrite:
        parser.error(f"output directory is not empty: {output}; choose a fresh directory or pass --overwrite")
    review_rows: list[dict[str, str]] = []
    tiles: list[Image.Image] = []
    for index, (source, path) in enumerate(selected, start=1):
        try:
            thumb, brightness, contrast = image_cues(path)
        except Exception as exc:
            print(f"Skipping unreadable image {path}: {exc}", file=sys.stderr)
            continue
        review_rows.append({
            "sample_id": f"{index:04d}", "source": source, "image_path": str(path),
            "brightness_mean_0_255": f"{brightness:.2f}",
            "contrast_stddev_0_255": f"{contrast:.2f}",
            "day_night_interior_uncertain": "", "rain_manual_uncertain": "uncertain",
            "reviewer_notes": "",
        })
        tile = Image.new("RGB", (260, 194), "white")
        tile.paste(thumb, ((260 - thumb.width) // 2, 4))
        draw = ImageDraw.Draw(tile)
        short_path = path.name
        if len(short_path) > 31:
            short_path = short_path[:28] + "..."
        source_label = source.replace("\\", "/").rstrip("/").split("/")
        source_label = "/".join(source_label[-2:]) if len(source_label) > 1 else source_label[0]
        if len(source_label) > 28:
            source_label = "..." + source_label[-25:]
        draw.text((7, 158), f"{index:04d} | {source_label}", fill="black")
        draw.text((7, 174), short_path, fill="black")
        tiles.append(tile)

    csv_out = output / "revisao.csv"
    fields = ["sample_id", "source", "image_path", "brightness_mean_0_255", "contrast_stddev_0_255",
              "day_night_interior_uncertain", "rain_manual_uncertain", "reviewer_notes"]
    with csv_out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review_rows)

    (output / "LEIA-ME.txt").write_text(
        "Revisão humana da amostra CityRain\n\n"
        "Use sample_id para relacionar cada linha às folhas de contato. image_path e source\n"
        "preservam o caminho e a proveniência da imagem original.\n\n"
        "Preencha day_night_interior_uncertain com: day, night, interior ou uncertain.\n"
        "Revise rain_manual_uncertain manualmente e troque uncertain por rain ou no_rain\n"
        "quando houver evidência visual suficiente. Deixe uncertain em caso de dúvida.\n\n"
        "brightness_mean_0_255 e contrast_stddev_0_255 são pistas calculadas em miniaturas;\n"
        "não determinam período do dia, chuva ou intensidade meteorológica. Nenhuma\n"
        "intensidade de chuva foi inferida.\n",
        encoding="utf-8",
    )

    columns = 5
    for start in range(0, len(tiles), args.sheet_size):
        batch = tiles[start:start + args.sheet_size]
        rows = math.ceil(len(batch) / columns)
        sheet = Image.new("RGB", (columns * 260, rows * 194), "#dddddd")
        for offset, tile in enumerate(batch):
            sheet.paste(tile, ((offset % columns) * 260, (offset // columns) * 194))
        sheet.save(output / f"contatos_{start // args.sheet_size + 1:02d}.jpg", quality=88, optimize=True)

    print(f"Sources: {len(groups)} | sampled: {len(review_rows)} | output: {output}")
    print(f"Review template: {csv_out}")
    for name, paths in groups.items():
        print(f"  {name}: {len(paths)} available, {quotas[name]} selected")
    print("Brightness/contrast are review cues only; day/night and rain labels require human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
