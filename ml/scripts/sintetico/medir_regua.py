"""Régua de chuva (D6): mede gotas no vidro, contraste ao longe e nitidez por frame.

Uso:
    ml/.venv/bin/python ml/scripts/sintetico/medir_regua.py [--grades]

Lê o manifest de rótulos (seco/garoa), os frames de 23/09 e os vídeos YouTube de chuva
forte; grava ``ml/configs/regua_chuva.json`` (média/desvio por grupo) e, com --grades,
grades de revisão com as gotas detectadas em ``ml/data/review/regua/``.

Todas as medições: frame redimensionado para largura 640, faixa inferior (capô/painel)
excluída. Determinístico (sem aleatoriedade; amostragem por stride uniforme).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

RAIZ = Path(__file__).resolve().parents[3]
ML = RAIZ / "ml"

PARAMS: dict = {
    "largura_norm": 640,
    "excluir_base_frac": 0.15,  # capô/painel na parte de baixo do quadro
    "dog_sigmas": [1.0, 1.5, 2.2],
    "dog_k": 1.6,
    "dog_limiar": 0.012,  # |G(s)-G(k s)| em intensidade 0..1
    "isotropia_min": 0.5,  # razão entre autovalores do Hessiano (1 = círculo)
    "textura_max": 0.015,  # só conta blobs sobre fundo liso (rejeita folhagem/fachada)
    "isolamento_janela": 41,  # px; média local da resposta
    "isolamento_razao": 3.5,  # pico / média local (rejeita textura densa: folhas)
    "raio_max_px": 4.0,
    "horizonte_faixa": [0.30, 0.60],  # fração da altura do quadro
    "ceu_saturado_gray": 225,  # >= : ignorado no contraste
    "ceu_dilatacao_px": 9,
    "contraste_local_janela": 9,
    "youtube_frames_por_video": 50,
    "faixas_garoa_mm_h": [0.9, 1.5],
}

# Presença de limpador: marcação MANUAL (olhando montagens com índice) de 50 frames, amostra
# uniforme por grupo (10 seco, 10 garoa 01/09, 10 garoa 13/09, 20 de 23/09). O detector
# automático não foi tentado de forma robusta: faixa escura diagonal confunde-se com asfalto,
# sombras e capô. Casos duvidosos contados como presentes só se a lâmina/rastro era visível.
LIMPADOR_MANUAL = {
    "metodo": "manual, 50 frames amostrados uniformemente, inspeção visual",
    "seco": {"n": 10, "com_limpador": 0},
    "garoa_01-09_0.6mm_h": {"n": 10, "com_limpador": 4},
    "garoa_13-09_1.2mm_h": {"n": 10, "com_limpador": 0},
    "chuva_2309": {"n": 20, "com_limpador": 8},
}

VIDEOS_YOUTUBE = ["frames7", "frames8", "frames11", "frames13", "frames14"]
PASTA_IMT = ML / "data" / "processed" / "imt_coleta"
PASTA_YT = ML / "data" / "processed" / "youtube"
MANIFEST = ML / "data" / "manifests" / "manifest_imt.csv"
SAIDA = ML / "configs" / "regua_chuva.json"
REVIEW = ML / "data" / "review" / "regua"


def normalizar(img: np.ndarray, largura: int = 640) -> np.ndarray:
    """Redimensiona para a largura dada preservando a proporção."""
    h, w = img.shape[:2]
    if w == largura:
        return img
    return cv2.resize(img, (largura, round(h * largura / w)), interpolation=cv2.INTER_AREA)


def recortar_roi(img: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Remove a faixa inferior (capô/painel)."""
    h = img.shape[0]
    return img[: int(h * (1 - params["excluir_base_frac"]))]


def detectar_gotas(gray: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Detecta blobs pequenos por diferença de gaussianas multi-escala.

    Args:
        gray: imagem em tons de cinza (uint8 ou float 0..1).
        params: parâmetros do detector.

    Returns:
        Array (N, 3) com colunas (x, y, raio_px).
    """
    g = gray.astype(np.float32)
    if gray.dtype == np.uint8:
        g = g / 255.0
    sig = params["dog_sigmas"]
    k = params["dog_k"]
    resp_l, iso_l = [], []
    for s in sig:
        resp_l.append(np.abs(ndi.gaussian_filter(g, s) - ndi.gaussian_filter(g, s * k)))
        # Hessian em escala s: blob = autovalores de mesmo sinal e razão próxima de 1
        # (rejeita bordas, fios e postes, que têm um autovalor ~0).
        hxx = ndi.gaussian_filter(g, s, order=(0, 2)) * s * s
        hyy = ndi.gaussian_filter(g, s, order=(2, 0)) * s * s
        hxy = ndi.gaussian_filter(g, s, order=(1, 1)) * s * s
        tr = hxx + hyy
        disc = np.sqrt(np.maximum((hxx - hyy) ** 2 / 4 + hxy**2, 0))
        l1, l2 = tr / 2 + disc, tr / 2 - disc
        menor = np.minimum(np.abs(l1), np.abs(l2))
        maior = np.maximum(np.abs(l1), np.abs(l2)) + 1e-9
        iso_l.append(np.where(l1 * l2 > 0, menor / maior, 0.0))
    pilha = np.stack(resp_l)
    textura = ndi.uniform_filter(pilha.max(axis=0), params["isolamento_janela"]) + 1e-6
    iso = np.stack(iso_l)
    pilha = np.where(iso >= params["isotropia_min"], pilha, 0.0)
    resp = pilha.max(axis=0)
    esc = pilha.argmax(axis=0)
    pico = (pilha == ndi.maximum_filter(pilha, size=(len(sig), 5, 5))).any(axis=0)
    ok = pico & (resp > params["dog_limiar"]) & (resp / textura > params["isolamento_razao"])
    if params.get("textura_max"):
        ok &= textura < params["textura_max"]
    ys, xs = np.nonzero(ok)
    raios = np.array(sig)[esc[ys, xs]] * np.sqrt(2.0)
    keep = raios <= params["raio_max_px"]
    return np.stack([xs[keep], ys[keep], raios[keep]], axis=1).astype(np.float32)


def contraste_horizonte(gray: np.ndarray, params: dict = PARAMS) -> tuple[float, float]:
    """Contraste da faixa do horizonte, ignorando céu saturado.

    Returns:
        (rms, local): desvio padrão do cinza na faixa e média do desvio local (janela
        pequena), ambos em 0..1. Em névoa os dois caem.
    """
    g = gray.astype(np.float32)
    h = g.shape[0]
    a, b = params["horizonte_faixa"]
    faixa = g[int(h * a) : int(h * b)]
    sat = faixa >= params["ceu_saturado_gray"]
    d = params["ceu_dilatacao_px"]
    sat = cv2.dilate(sat.astype(np.uint8), np.ones((d, d), np.uint8)).astype(bool)
    valido = ~sat
    if valido.mean() < 0.1:
        return float("nan"), float("nan")
    j = params["contraste_local_janela"]
    media = ndi.uniform_filter(faixa, j)
    var = np.maximum(ndi.uniform_filter(faixa * faixa, j) - media * media, 0)
    return float(faixa[valido].std() / 255.0), float(np.sqrt(var)[valido].mean() / 255.0)


def var_laplaciano(gray: np.ndarray) -> float:
    """Variância do Laplaciano (nitidez global)."""
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def medir_imagem(bgr: np.ndarray, params: dict = PARAMS) -> dict:
    """Todas as métricas de um frame BGR (já normalizado ou não)."""
    img = recortar_roi(normalizar(bgr, params["largura_norm"]), params)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gotas = detectar_gotas(gray, params)
    mp = gray.shape[0] * gray.shape[1] / 1e6
    rms, loc = contraste_horizonte(gray, params)
    return {
        "gotas_mp": len(gotas) / mp,
        "raio_medio_px": float(gotas[:, 2].mean()) if len(gotas) else float("nan"),
        "raio_p90_px": float(np.percentile(gotas[:, 2], 90)) if len(gotas) else float("nan"),
        "frac_gotas_grandes": float((gotas[:, 2] >= 2.5).mean()) if len(gotas) else float("nan"),
        "contraste_rms": rms,
        "contraste_local": loc,
        "var_laplaciano": var_laplaciano(gray),
    }


def _resumo(linhas: list[dict]) -> dict:
    out: dict = {"n": len(linhas)}
    for k in linhas[0]:
        v = np.array([l[k] for l in linhas], dtype=float)
        v = v[~np.isnan(v)]
        out[k] = {"media": round(float(v.mean()), 5), "desvio": round(float(v.std()), 5)} if len(v) else None
    return out


def listar_grupos(params: dict = PARAMS) -> tuple[dict[str, list[Path]], dict]:
    """Monta {grupo: [caminhos]} e as contagens do manifest usado."""
    cortes = params["faixas_garoa_mm_h"]
    with open(MANIFEST, newline="") as f:
        linhas = list(csv.DictReader(f))
    grupos: dict[str, list[Path]] = {}
    contagem: dict = {"linhas": len(linhas), "por_evento_classe": {}}
    for r in linhas:
        if r["classe"] not in ("seco", "garoa"):
            continue
        p = PASTA_IMT / r["pasta"] / r["arquivo"]
        ev = r["evento_id"].split("__")[-1]
        if r["classe"] == "seco":
            chave = f"seco_{ev}"
        else:
            mm = float(r["mm_h"])
            lim = [0.0, *cortes, 1e9]
            i = max(j for j in range(len(lim) - 1) if mm > lim[j] or j == 0)
            chave = f"garoa_mm_h_{lim[i]:g}_{lim[i + 1]:g}".replace("_1e+09", "_inf")
        grupos.setdefault(chave, []).append(p)
        k = f"{ev}:{r['classe']}"
        contagem["por_evento_classe"][k] = contagem["por_evento_classe"].get(k, 0) + 1
    contagem["sha256"] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()[:16]
    grupos["chuva_2309"] = sorted((PASTA_IMT / "cityrain_frames4").glob("frame_20260923_*.jpg"))
    n = params["youtube_frames_por_video"]
    for v in VIDEOS_YOUTUBE:
        todos = sorted((PASTA_YT / v).glob("*.jpg"))
        idx = np.linspace(0, len(todos) - 1, min(n, len(todos))).round().astype(int)
        grupos[f"youtube_{v}"] = [todos[i] for i in idx]
    return grupos, contagem


def desenhar(bgr: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Frame normalizado com gotas (círculos) e limites da ROI/horizonte."""
    img = normalizar(bgr, params["largura_norm"]).copy()
    roi = recortar_roi(img, params)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    for x, y, r in detectar_gotas(gray, params):
        cv2.circle(img, (int(x), int(y)), int(round(r)) + 2, (0, 255, 0), 1)
    h = img.shape[0]
    cv2.line(img, (0, roi.shape[0]), (img.shape[1], roi.shape[0]), (0, 0, 255), 1)
    a, b = params["horizonte_faixa"]
    for f in (a, b):
        cv2.line(img, (0, int(h * f)), (12, int(h * f)), (255, 255, 0), 2)
    return img


def grade(caminhos: list[Path], rotulo: str, destino: Path | str, colunas: int = 3) -> None:
    """Grava uma grade com as gotas detectadas sobrepostas."""
    tiles = []
    for p in caminhos:
        im = cv2.imread(str(p))
        t = desenhar(im)
        n = len(detectar_gotas(cv2.cvtColor(recortar_roi(normalizar(im)), cv2.COLOR_BGR2GRAY)))
        t = cv2.resize(t, (640, 360)) if t.shape[0] != 360 else t
        cv2.putText(t, f"{rotulo} n={n}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        tiles.append(t)
    while len(tiles) % colunas:
        tiles.append(np.zeros_like(tiles[0]))
    linhas = [np.hstack(tiles[i : i + colunas]) for i in range(0, len(tiles), colunas)]
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destino), np.vstack(linhas), [cv2.IMWRITE_JPEG_QUALITY, 85])


def _amostra(l: list[Path], n: int) -> list[Path]:
    idx = np.linspace(0, len(l) - 1, n).round().astype(int)
    return [l[i] for i in idx]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grades", action="store_true", help="gera grades de revisão")
    args = ap.parse_args()

    grupos, contagem = listar_grupos()
    saida: dict = {
        "manifest_usado": {"arquivo": str(MANIFEST.relative_to(RAIZ)), **contagem},
        "parametros_detector": PARAMS,
        "unidades": "frame normalizado em largura 640; ROI sem faixa inferior; gotas_mp = por megapixel da ROI",
        "limpador_manual": LIMPADOR_MANUAL,
        "grupos": {},
    }
    todas: dict[str, list[dict]] = {}
    for nome, caminhos in grupos.items():
        linhas = [medir_imagem(cv2.imread(str(p))) for p in caminhos]
        saida["grupos"][nome] = _resumo(linhas)
        todas[nome] = linhas
        print(nome, len(linhas))
    for agg, prefixo in (("garoa_todas", "garoa_"), ("seco_todas", "seco_")):
        juntas = [l for n, v in todas.items() if n.startswith(prefixo) for l in v]
        saida["grupos"][agg] = _resumo(juntas)
    SAIDA.write_text(json.dumps(saida, indent=2, ensure_ascii=False))
    print("escrito", SAIDA)
    if args.grades:
        for nome, caminhos in grupos.items():
            grade(_amostra(caminhos, 6), nome, REVIEW / f"grade_{nome}.jpg")


if __name__ == "__main__":
    main()
