#!/usr/bin/env python3
"""Inventário retomável de arquivos de imagem, sem carregar imagens na RAM.

Uso: python inventario_acervo.py [--root PATH] [--output-dir PATH]
Retomar uma execução usa o mesmo diretório de saída. --self-test exercita
hashes duplicados e classificação de máscaras com uma fixture temporária.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif", ".ppm", ".pgm"}
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages", "cache", "caches"}


def role_for(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    partset = set(parts)
    name = path.name.lower()
    if any(p in {"mask", "masks", "ground-truth-label", "ground_truth", "ground-truth", "annotations"} for p in parts) or any(k in name for k in ("_mask.", "_gt.", "groundtruth")):
        return "mask"
    if any(k in p for p in parts for k in ("candidate", "uncertain", "duvid", "revisar")):
        return "candidate_uncertain"
    if any(p in {"assets", "static", "screenshots", "figures", "_amostras"} for p in parts) or "frontend" in partset:
        return "non_dataset"
    # Frames extracted from videos remain source photographs even under processed/youtube.
    if "processed" in partset and "youtube" in partset:
        return "photo"
    if any(p in {"derived", "preprocessamento", "augmentations", "thumbnails", "previews", "processed"} for p in parts):
        return "derived"
    return "photo"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, data: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def inventory(root: Path, out: Path) -> dict:
    root = root.resolve()
    out = out.resolve()
    if out == root:
        raise ValueError("Output directory must differ from inventory root")
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoint.json"
    saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    cache = saved.get("records", {}) if saved.get("root") == str(root) else {}
    paths: list[Path] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d.lower() not in EXCLUDED_DIRS and not (Path(current) / d).is_symlink() and (Path(current) / d).resolve() != out)
        for name in files:
            p = Path(current) / name
            if p.suffix.lower() in IMAGE_EXTENSIONS and not p.is_symlink():
                paths.append(p)
    paths.sort(key=lambda p: p.relative_to(root).as_posix().casefold())
    records = []
    errors = []
    for idx, path in enumerate(paths, 1):
        rel = path.relative_to(root).as_posix()
        try:
            st = path.stat()
            cached = cache.get(rel, {})
            if cached.get("size_bytes") == st.st_size and cached.get("mtime_ns") == st.st_mtime_ns and cached.get("sha256"):
                row = {**cached, "role": role_for(Path(rel))}
            else:
                row = {
                    "relative_path": rel, "size_bytes": st.st_size,
                    "origin_folder": Path(rel).parent.as_posix() if "/" in rel else ".",
                    "role": role_for(Path(rel)), "sha256": sha256_file(path) if st.st_size else "",
                    "zero_bytes": st.st_size == 0, "mtime_ns": st.st_mtime_ns,
                }
            records.append(row)
        except (OSError, PermissionError) as exc:
            errors.append({"relative_path": rel, "error": str(exc)})
        if idx % 5000 == 0:
            atomic_json(checkpoint, {"root": str(root), "records": {r["relative_path"]: r for r in records}})
            print(f"hashed/scanned {idx}/{len(paths)}", flush=True)
    atomic_json(checkpoint, {"root": str(root), "records": {r["relative_path"]: r for r in records}})
    groups: dict[str, list[str]] = defaultdict(list)
    for row in records:
        if row["sha256"]:
            groups[row["sha256"]].append(row["relative_path"])
    duplicate_groups = [sorted(v) for v in groups.values() if len(v) > 1]
    role_counts = Counter(r["role"] for r in records)
    summary = {
        "root": str(root), "image_file_count": len(records), "total_bytes": sum(r["size_bytes"] for r in records),
        "zero_byte_count": sum(r["zero_bytes"] for r in records), "hash_error_count": len(errors),
        "exact_duplicate_groups": len(duplicate_groups), "files_in_exact_duplicate_groups": sum(map(len, duplicate_groups)),
        "unique_nonempty_sha256": len(groups), "role_counts": dict(sorted(role_counts.items())),
        "training_photo_candidates": role_counts["photo"] + role_counts["candidate_uncertain"],
        "errors": errors,
        "note": "origin_folder is filesystem provenance only; timestamps are not interpreted as capture sessions. Masks and derived files are excluded from training_photo_candidates.",
    }
    manifest = out / "manifest.csv"
    fields = ["relative_path", "size_bytes", "origin_folder", "role", "sha256", "zero_bytes"]
    with manifest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({k: row[k] for k in fields})
    atomic_json(out / "summary.json", summary)
    atomic_json(out / "duplicate_groups.json", duplicate_groups)
    return summary


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "root"
        (root / "photos").mkdir(parents=True)
        (root / "ground-truth-label").mkdir()
        (root / "processed" / "youtube").mkdir(parents=True)
        (root / "photos" / "a.jpg").write_bytes(b"same")
        (root / "photos" / "b.JPG").write_bytes(b"same")
        (root / "ground-truth-label" / "a.png").write_bytes(b"mask")
        (root / "processed" / "youtube" / "frame.jpg").write_bytes(b"video frame")
        out = Path(td) / "out"
        first = inventory(root, out)
        second = inventory(root, out)
        assert first["exact_duplicate_groups"] == 1
        assert first["role_counts"]["mask"] == 1
        assert first["role_counts"]["photo"] == 3
        assert first["training_photo_candidates"] == 3
        assert second == first
        print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp/cityrain-inventario"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    summary = inventory(args.root, args.output_dir)
    print(json.dumps({k: summary[k] for k in ("image_file_count", "total_bytes", "zero_byte_count", "exact_duplicate_groups", "role_counts")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
