#!/usr/bin/env python3
"""Replay de uma chuva real gravada por uma câmera fixa, pelo pipeline de produção (spec CF8).

Cada frame do evento é reenviado ao POST /api/v1/ingest como se fosse agora, com
`metadata.demo` (o histórico exclui demo). O backend deduplica por sha256 da imagem,
então cada envio ganha um comentário JPEG com a hora do replay: os pixels são os
mesmos, o hash não, e o replay pode ser ensaiado quantas vezes for preciso.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/replay_evento.py --camera bc_atlantica \
        --de 2026-10-01T18:00:00-03:00 --ate 2026-10-01T19:00:00-03:00 --intervalo 2
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, time as hora, timedelta, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from coletor import enviar_frame, token_da_fonte  # noqa: E402


def com_marca_de_replay(jpeg: bytes, marca: str) -> bytes:
    """Insere um segmento COM logo após o SOI; não toca nos dados da imagem."""
    if not jpeg.startswith(b"\xff\xd8"):
        raise ValueError("não é JPEG")
    texto = f"cityrain-replay:{marca}".encode()
    seg = b"\xff\xfe" + (len(texto) + 2).to_bytes(2, "big") + texto
    return jpeg[:2] + seg + jpeg[2:]


FUSO_LOCAL = timezone(timedelta(hours=-3))  # mesma regra do backend e do rotulador (UTC-3)


def periodo_local(t: datetime) -> str:
    """'dia' se o horário local (UTC-3) está em [06:00, 18:30), senão 'noite'."""
    local = t.astimezone(FUSO_LOCAL).time()
    return "dia" if hora(6, 0) <= local < hora(18, 30) else "noite"


def periodo_agora() -> str:
    return periodo_local(datetime.now(timezone.utc))


def parse_instante(texto: str, nome: str) -> tuple[datetime, bool]:
    """Lê um ISO 8601. Sem fuso, assume -03:00. Devolve (instante, fuso_assumido)."""
    try:
        t = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{nome}: data inválida {texto!r}; use ISO 8601, ex.: 2026-10-01T18:00:00-03:00") from None
    if t.tzinfo is None:
        return t.replace(tzinfo=FUSO_LOCAL), True
    return t, False


def _quando(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def periodos_dos_frames(frames: list[Path]) -> set[str]:
    """Períodos (dia/noite) dos horários ORIGINAIS de captura dos frames."""
    return {periodo_local(_quando(json.loads(f.with_suffix(".json").read_text())["capturado_em_utc"])) for f in frames}


def selecionar_frames(manifest: Path, camera: str, de: datetime | None, ate: datetime | None, raiz_frames: Path) -> list[Path]:
    with open(manifest, newline="") as f:
        linhas = [r for r in csv.DictReader(f) if r["pasta"] == camera]
    escolhidos = []
    for r in sorted(linhas, key=lambda r: r["ts_utc"]):
        t = _quando(r["ts_utc"])
        if (de and t < de) or (ate and t > ate):
            continue
        p = raiz_frames / camera / r["arquivo"]
        if p.is_file() and p.with_suffix(".json").is_file():
            escolhidos.append(p)
    return escolhidos


def preparar_frame_replay(jpg: Path, destino: Path, agora: datetime, marca: str) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    meta = json.loads(jpg.with_suffix(".json").read_text())
    meta["capturado_originalmente"] = meta["capturado_em_utc"]
    meta["capturado_em_utc"] = agora.isoformat()
    novo = destino / jpg.name
    novo.write_bytes(com_marca_de_replay(jpg.read_bytes(), marca))
    novo.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False))
    return novo


def enviar_todos(frames: list[Path], url: str, token: str, camera: str, intervalo: float,
                 enviar=enviar_frame, dormir=time.sleep) -> dict:
    """Reenvia os frames como se fossem agora. Aborta no primeiro 4xx que não seja 409 (duplicado)."""
    r = {"ok": 0, "duplicados": 0, "erros": 0, "sem_rede": 0, "abortado": None}
    tmp = Path(tempfile.mkdtemp(prefix="replay_"))
    try:
        for i, jpg in enumerate(frames):
            agora = datetime.now(timezone.utc)
            novo = preparar_frame_replay(jpg, tmp, agora, agora.isoformat())
            original = json.loads(novo.with_suffix(".json").read_text())["capturado_originalmente"]
            demo = {"origem": "replay_evento", "camera": camera, "capturado_originalmente": original}
            status = enviar(novo, url, token, demo=demo)
            print(f"  {jpg.name} (gravado {original}) -> {status or 'sem rede'}", flush=True)
            if status == 0:
                r["sem_rede"] += 1
            elif 200 <= status < 300:
                r["ok"] += 1
            elif status == 409:
                r["duplicados"] += 1
            elif 400 <= status < 500:
                r["erros"] += 1
                r["abortado"] = status
                break
            else:
                r["erros"] += 1
            if i < len(frames) - 1:
                dormir(intervalo)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--de", help="início (ISO 8601; sem fuso assume -03:00)")
    ap.add_argument("--ate", help="fim (ISO 8601; sem fuso assume -03:00)")
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--forcar-periodo", action="store_true",
                    help="envia mesmo se o período (dia/noite) dos frames difere do de agora")
    ap.add_argument("--manifest", type=Path, default=RAIZ / "ml/data/manifests/manifest_coleta_fixa.csv")
    ap.add_argument("--raiz-frames", type=Path, default=RAIZ / "ml/data/raw/coleta_fixa")
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/coleta_fixa.yaml")
    ap.add_argument("--tokens", type=Path, default=RAIZ / "ml/configs/coleta_fixa_tokens.json")
    ap.add_argument("--api", help="URL do /ingest (default: backend_url do YAML)")
    args = ap.parse_args()

    limites = []
    for texto, nome in ((args.de, "--de"), (args.ate, "--ate")):
        if not texto:
            limites.append(None)
            continue
        try:
            t, assumido = parse_instante(texto, nome)
        except ValueError as e:
            ap.error(str(e))
        if assumido:
            print(f"[replay] {nome} sem fuso: assumindo -03:00 ({t.isoformat()})", flush=True)
        limites.append(t)
    de, ate = limites

    url = args.api or yaml.safe_load(args.config.read_text())["backend_url"]
    token = token_da_fonte(args.camera, args.tokens)
    if not token:
        sys.exit(f"sem token para {args.camera}: defina CITYRAIN_TOKEN_{args.camera.upper()} ou {args.tokens}")
    frames = selecionar_frames(args.manifest, args.camera, de, ate, args.raiz_frames)
    if not frames:
        sys.exit(f"[replay] nenhum frame selecionado para {args.camera} nessa janela. Confira --camera (id da fonte, "
                 f"ex.: bc_atlantica) e --de/--ate; se baixou DVR novo, regenere o manifest ({args.manifest}).")

    periodos = periodos_dos_frames(frames)
    agora_p = periodo_agora()
    if periodos != {agora_p}:
        msg = (f"os frames são de período {'/'.join(sorted(periodos))} e agora é {agora_p}: o backend escolhe a "
               f"referência seca pelo horário do envio (UTC-3, dia = [06:00, 18:30)), então a classificação sairia "
               f"com a referência errada.")
        if not args.forcar_periodo:
            sys.exit(f"[replay] abortado: {msg} Use --forcar-periodo para enviar assim mesmo.")
        print(f"[replay] ATENÇÃO (--forcar-periodo): {msg}", flush=True)

    print(f"[replay] {len(frames)} frames de {args.camera} -> {url}", flush=True)
    r = enviar_todos(frames, url, token, args.camera, args.intervalo)
    print(f"[replay] resumo: {r['ok']} enviados ok, {r['duplicados']} duplicados, {r['erros']} erros, "
          f"{r['sem_rede']} sem rede", flush=True)
    if r["abortado"]:
        sys.exit(f"[replay] abortado no HTTP {r['abortado']}: token errado (401/403) ou dispositivo que não é "
                 f"'fixa' / dados inválidos (422). Confira o token da câmera e o cadastro do dispositivo.")


if __name__ == "__main__":
    main()
