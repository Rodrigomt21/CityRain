import csv
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE = Path(__file__).parent
ML_DIR = BASE.parents[1]
RAW_VIDEOS_DIR = ML_DIR / "data" / "raw" / "public_datasets" / "youtube" / "videos"
PROCESSED_DIR = ML_DIR / "data" / "processed" / "youtube"

LINKS_FILE = BASE / "links.txt"
MANIFEST_FILE = PROCESSED_DIR / "manifest.csv"
FPS = 1               # frames por segundo extraídos
QUALIDADE_JPG = 2     # 2 = alta qualidade (escala 2..31, menor = melhor)
NAVEGADOR_COOKIES = "chrome"   # chrome | safari | firefox | edge | brave — None p/ desativar

# yt-dlp com curl-cffi (Cloudflare bypass) preferencialmente; fallback no PATH
_VENV_YTDLP = ML_DIR / ".venv" / "bin" / "yt-dlp"
YTDLP = str(_VENV_YTDLP) if _VENV_YTDLP.exists() else "yt-dlp"


def parse_linha(linha: str) -> tuple[str, str] | None:
    """Retorna (url, tags) ou None se for comentário/vazio.

    Formato: URL [<espaços># tag1 | tag2 | ...]
    """
    linha = linha.strip()
    if not linha or linha.startswith("#"):
        return None
    if "#" in linha:
        url, _, tags = linha.partition("#")
        return url.strip(), tags.strip()
    return linha, ""


def detectar_fonte(url: str) -> tuple[str, str]:
    """Retorna (source, source_id) ex: ('youtube', 'YiJ3RAWeQLQ') ou ('pexels', '33523296')."""
    p = urlparse(url)
    host = p.netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        if "youtu.be" in host:
            return "youtube", p.path.lstrip("/").split("/")[0]
        qs = parse_qs(p.query)
        if "v" in qs:
            return "youtube", qs["v"][0]
        return "youtube", p.path.rstrip("/").split("/")[-1]
    if "pexels.com" in host:
        m = re.search(r"-(\d+)/?$", p.path)
        if m:
            return "pexels", m.group(1)
        return "pexels", p.path.rstrip("/").split("/")[-1]
    return host or "outro", p.path.rstrip("/").split("/")[-1]


def eh_playlist_ou_canal(url: str) -> bool:
    """Apenas para URLs do YouTube. Pexels/outras nunca são playlist."""
    if "youtube.com" not in url and "youtu.be" not in url:
        return False
    marcadores = ("/playlist", "list=", "/@", "/channel/", "/c/", "/user/")
    if any(m in url for m in marcadores):
        return True
    cauda = url.rstrip("/").split("/")[-1]
    return "watch" not in url and "youtu.be" not in url and "?" not in cauda and "=" not in cauda


def baixar_video(link: str, destino: Path) -> bool:
    if destino.exists() and destino.stat().st_size > 0:
        print(f"  ↷ vídeo já baixado ({destino.stat().st_size / 1e6:.0f} MB) — pulando download")
        return True
    eh_youtube = "youtube.com" in link or "youtu.be" in link
    cmd = [YTDLP, "--no-playlist", "-f", "best[ext=mp4]/best", "-o", str(destino)]
    if eh_youtube and NAVEGADOR_COOKIES:
        cmd += ["--cookies-from-browser", NAVEGADOR_COOKIES]
    if not eh_youtube:
        # Pexels e similares ficam atrás do Cloudflare — usa impersonação via curl-cffi
        cmd += ["--extractor-args", "generic:impersonate"]
    cmd += ["--", link]
    try:
        subprocess.run(cmd, check=True)
        return destino.exists() and destino.stat().st_size > 0
    except subprocess.CalledProcessError as e:
        print(f"  ✗ erro no yt-dlp (código {e.returncode})")
        return False


def extrair_frames(video: Path, pasta: Path) -> bool:
    pasta.mkdir(exist_ok=True)
    existentes = list(pasta.glob("frame_*.jpg"))
    if existentes:
        print(f"  ↷ {len(existentes)} frames já em {pasta.name}/ — pulando extração")
        return True
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", str(video),
        "-vf", f"fps={FPS}",
        "-q:v", str(QUALIDADE_JPG),
        str(pasta / "frame_%05d.jpg"),
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ erro no ffmpeg (código {e.returncode})")
        return False


def duracao_segundos(video: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def main():
    if not LINKS_FILE.exists():
        sys.exit(f"Arquivo {LINKS_FILE} não encontrado")

    RAW_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    entradas = []
    for linha in LINKS_FILE.read_text(encoding="utf-8").splitlines():
        parsed = parse_linha(linha)
        if parsed:
            entradas.append(parsed)

    total = len(entradas)
    sucesso, falhas, pulados = 0, [], []
    manifest_rows = []

    for i, (link, tags) in enumerate(entradas, start=1):
        print(f"\n[{i}/{total}] {link}")
        if tags:
            print(f"    tags: {tags}")

        if eh_playlist_ou_canal(link):
            print(f"  ⚠ URL de playlist/canal — substitua por links de vídeos individuais")
            pulados.append((i, link))
            continue

        source, source_id = detectar_fonte(link)
        video = RAW_VIDEOS_DIR / f"video{i}.mp4"
        pasta = PROCESSED_DIR / f"frames{i}"

        if not baixar_video(link, video):
            falhas.append((i, link, "download"))
            manifest_rows.append({
                "idx": i, "url": link, "source": source, "source_id": source_id,
                "tags": tags, "size_mb": 0, "duration_s": 0, "n_frames": 0, "status": "falha_download",
            })
            continue
        if not extrair_frames(video, pasta):
            falhas.append((i, link, "frames"))
            manifest_rows.append({
                "idx": i, "url": link, "source": source, "source_id": source_id,
                "tags": tags,
                "size_mb": round(video.stat().st_size / 1e6, 1),
                "duration_s": round(duracao_segundos(video), 1),
                "n_frames": 0, "status": "falha_frames",
            })
            continue

        n_frames = len(list(pasta.glob("frame_*.jpg")))
        size_mb = round(video.stat().st_size / 1e6, 1)
        dur = round(duracao_segundos(video), 1)
        print(f"  ✓ vídeo {i} OK — {n_frames} frames em {pasta.name}/ ({size_mb} MB, {dur:.0f}s)")
        sucesso += 1
        manifest_rows.append({
            "idx": i, "url": link, "source": source, "source_id": source_id,
            "tags": tags, "size_mb": size_mb, "duration_s": dur,
            "n_frames": n_frames, "status": "ok",
        })

    with MANIFEST_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "idx", "url", "source", "source_id", "tags",
            "size_mb", "duration_s", "n_frames", "status",
        ])
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\n{'=' * 50}")
    print(f"Resumo: {sucesso} OK | {len(falhas)} falha(s) | {len(pulados)} pulado(s)")
    print(f"Manifest: {MANIFEST_FILE.relative_to(ML_DIR)}")
    total_frames = sum(r["n_frames"] for r in manifest_rows)
    print(f"Total de frames extraídos: {total_frames}")
    for i, link, etapa in falhas:
        print(f"  ✗ [{i}] falhou em '{etapa}': {link}")
    for i, link in pulados:
        print(f"  ⚠ [{i}] pulado (playlist/canal): {link}")


if __name__ == "__main__":
    main()
