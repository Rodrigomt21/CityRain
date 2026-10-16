"""Forte de para-brisa: vídeos de câmera veicular do YouTube (EUA) rotulados pelo radar MRMS.

A câmera grava data/hora (e às vezes GPS) na imagem. A cada ``PASSO_S`` segundos de vídeo:
OCR do relógio (+ GPS) -> UTC (com o desvio do relógio da câmera, fixado por vídeo a partir do
horário público do evento) -> radar MRMS PrecipRate em t0 e ±2 min -> classe pela mesma regra do
BDD (nucleo.decidir). Os vídeos têm cortes, então o relógio é lido em TODO frame; frame sem
leitura do relógio é descartado. Só dia (elevação do sol > 0) e recorte central 4:3.

Sem GPS na imagem o local é o da cidade/evento: a regra vira por ÁREA (janela de ``raio_km``):
classe da mediana da janela e ambíguo se < 80% das células têm essa classe ou se ±2 min discordam.

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_youtube/dashcam_radar.py
Saída: data/processed/youtube/dashcam_eua/<id>/*.jpg e data/manifests/dashcam_eua_mrms.csv
"""
import math, re, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import cv2, numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bdd"))
import mrms
from nucleo import url_mrms, timestamp_mrms_mais_proximo, decidir, classe_de, mrms_valido

VID = Path("data/raw/public_datasets/youtube/dashcam_eua")
OUT = Path("data/processed/youtube/dashcam_eua")
MAN = Path("data/manifests/dashcam_eua_mrms.csv")
PASSO_S = 4

# id -> recorte do texto (x0, y0, largura, altura em fração), regex, formato, desvio do relógio
# (UTC = relógio - desvio_h) e local fixo (lat, lon, raio_km) quando não há GPS na imagem.
VIDEOS = {
    # Houston, derecho de 16/05/2024; VIOFO A129 com GPS. Relógio 5 h à frente do UTC: o derecho
    # passou no NW de Houston ~18h15 CDT (23h15 UTC) e a câmera mostra 04h1x do dia 17.
    "BEl8JZr-NHY": dict(ocr=[(0, .96, 1, .04)], neg=True,
                        re=r"N(?P<lat>\d+\.\s?\d+)\s+W(?P<lon>\d+\.\s?\d+).*?(?P<t>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
                        fmt="%Y-%m-%d %H:%M:%S", desvio_h=5),
    # Houston, mesmo derecho, outra câmera (Vantrue, GPS). Relógio = UTC-3: a chuva pesada do vídeo
    # (20h09-20h30 no relógio) bate com a passagem pública do derecho no W de Houston (23h15-23h30 UTC).
    "lib41z-4zVk": dict(ocr=[(0, .94, 1, .05)],
                        re=r"(?P<t>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?N\s?(?P<lat>\d{2}\.\d{4,})\s+W\s?(?P<lon>\d{2,3}\.\d{4,})",
                        fmt="%Y/%m/%d %H:%M:%S", desvio_h=-3),
    # Rockford/Cherry Valley (IL), derecho de 10/08/2020 ~14h50 CDT; Rove R2-4K com GPS.
    "HRL2l7OVQJs": dict(ocr=[(0, .94, .5, .05), (.5, .94, .5, .05)],
                        re=r"(?P<t>\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} ?[AP]M).*?N(?P<lat>\d{2}\.\s?\d{4,})\s+W(?P<lon>\d{2,3}\.\s?\d{4,})",
                        fmt="%m/%d/%Y %I:%M:%S%p", desvio_h=-5),
    # SE de Iowa (New London / Mount Pleasant), 07/05/2023 ~18h50 CDT; COOAU D30, GPS em graus-minutos.
    "aQCu0Xv3ufY": dict(ocr=[(0, .94, 1, .05)],
                        re=r"(?P<t>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?N(?P<lat>\d{2})°(?P<latm>\d{2}\.\d+)\s+W(?P<lon>\d{2,3})°(?P<lonm>\d{2}\.\d+)",
                        fmt="%Y/%m/%d %H:%M:%S", desvio_h=-5),
    # Sem GPS (regra por área): Dallas 09/06/2019, Ankeny 10/06/2026, Imelda 19/09/2019 (7300 N. Shepherd).
    "43jbrvd_KkA": dict(ocr=[(0, .94, .5, .06)], re=r"(?P<t>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})",
                        fmt="%Y/%m/%d %H:%M:%S", desvio_h=-5, local=(32.78, -96.80, 10)),
    "aKm2CW3CQcg": dict(ocr=[(.5, .94, .5, .06)], re=r"(?P<t>\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}[AP]M)",
                        fmt="%d-%m-%Y %I:%M:%S%p", desvio_h=-5, local=(41.73, -93.60, 10)),
    "cG3oG9QxjVg": dict(ocr=[(0, .94, 1, .05)], re=r"(?P<t>\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})",
                        fmt="%Y.%m.%d %H:%M:%S", desvio_h=-5, local=(29.85, -95.41, 5)),
}


def elevacao_sol(lat, lon, t):
    """Elevação aproximada do sol em graus (NOAA simplificado; erro < 1°, suficiente p/ dia x noite)."""
    d = t.timetuple().tm_yday + (t.hour + t.minute / 60) / 24
    g = 2 * math.pi / 365 * (d - 1)
    decl = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) \
        + 0.000907 * math.sin(2 * g)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                    - 0.040849 * math.sin(2 * g))
    ha = math.radians(((t.hour * 60 + t.minute + eqt + 4 * lon) / 4) - 180)
    la = math.radians(lat)
    return math.degrees(math.asin(math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)))


def ler_texto(img, cfg):
    """OCR das faixas do vídeo (uma ou mais), concatenadas."""
    h, w = img.shape[:2]
    partes = []
    for x0, y0, cw, ch in cfg["ocr"]:
        faixa = cv2.cvtColor(img[int(h * y0):int(h * (y0 + ch)), int(w * x0):int(w * (x0 + cw))], cv2.COLOR_BGR2GRAY)
        faixa = cv2.resize(faixa, None, fx=2, fy=2)
        if cfg.get("neg"):
            faixa = 255 - faixa
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            cv2.imwrite(f.name, faixa)
            partes.append(subprocess.run(["tesseract", f.name, "-", "--psm", "7"], capture_output=True, text=True).stdout)
    return " ".join(p.strip() for p in partes)


def ocr(img, cfg, desvio_h=None):
    """(UTC, lat, lon, raio_km) ou None. raio_km = 0 quando o GPS veio da imagem."""
    m = re.search(cfg["re"], ler_texto(img, cfg))
    if not m:
        return None
    g = m.groupdict()
    desvio = cfg["desvio_h"] if desvio_h is None else desvio_h
    try:
        t = datetime.strptime(g["t"].replace(" PM", "PM").replace(" AM", "AM"), cfg["fmt"]).replace(tzinfo=timezone.utc) \
            - timedelta(hours=desvio)
    except ValueError:
        return None
    if g.get("lat"):
        lat, lon = float(g["lat"].replace(" ", "")), float(g["lon"].replace(" ", ""))
        if g.get("latm"):
            lat, lon = lat + float(g["latm"]) / 60, lon + float(g["lonm"]) / 60
        if lat == 0:  # câmera sem fix de GPS
            return None
        return t, lat, -lon, 0
    return (t, *cfg["local"])


_cache = {}


def campo(ts):
    if ts not in _cache:
        b = mrms.baixar(url_mrms(ts))
        _cache[ts] = mrms.campo(b) if b is not None else None
    return _cache[ts]


def rotular(t, lat, lon, raio_km):
    ts0 = timestamp_mrms_mais_proximo(t)
    i, j = mrms.indice(lat, lon)
    r = max(1, raio_km)
    jan = {o: (campo(ts0 + timedelta(minutes=o))) for o in (0, -2, 2)}
    if jan[0] is None:
        return None, True, "sem_dado_mrms", None
    if raio_km == 0:  # GPS: regra do BDD (ponto, 3x3, ±2 min)
        v = jan[0]
        viz = [mrms_valido(x) for x in v[i - 1:i + 2, j - 1:j + 2].ravel()]
        t2 = [mrms_valido(jan[o][i, j]) if jan[o] is not None else None for o in (-2, 2)]
        c, amb, mot = decidir(mrms_valido(v[i, j]), viz, t2, [None, None])
        return c, amb, mot, mrms_valido(v[i, j])
    # sem GPS: regra por área
    def area(v):
        w = v[i - r:i + r + 1, j - r:j + r + 1].ravel()
        return w[w >= 0]
    w = area(jan[0])
    med = float(np.median(w))
    c = classe_de(med)
    frac = np.mean([classe_de(x) == c for x in w])
    outras = [classe_de(float(np.median(area(jan[o])))) for o in (-2, 2) if jan[o] is not None]
    if frac < 0.8:
        return c, True, f"area_heterogenea_{frac:.2f}", med
    if any(o != c for o in outras):
        return c, True, "instavel_2min", med
    return c, False, "", med


def main():
    linhas = []
    for vid, cfg in VIDEOS.items():
        dest = OUT / vid; dest.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(VID / f"{vid}.mp4"))
        dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
        n = 0
        for s in np.arange(0, dur, PASSO_S):
            cap.set(cv2.CAP_PROP_POS_MSEC, s * 1000)
            ok, img = cap.read()
            if not ok:
                continue
            lido = ocr(img, cfg)
            if lido is None:
                linhas.append(dict(video=vid, seg=s, motivo="ocr_falhou")); continue
            t, lat, lon, raio = lido
            dia = elevacao_sol(lat, lon, t) > 0
            c, amb, mot, mm = rotular(t, lat, lon, raio)
            h, w = img.shape[:2]
            cw = round(h * 4 / 3); x0 = (w - cw) // 2
            nome = f"{vid}_{int(s):05d}.jpg"
            topo_texto = min(y0 for _, y0, _, _ in cfg["ocr"])  # tira a faixa do relógio/GPS da imagem
            cv2.imwrite(str(dest / nome), img[:int(h * topo_texto), x0:x0 + cw], [cv2.IMWRITE_JPEG_QUALITY, 92])
            linhas.append(dict(video=vid, seg=s, imagem=f"{vid}/{nome}", utc=t.isoformat(), lat=lat, lon=lon,
                               raio_km=raio, dia=dia, mm_h=mm, classe=c, ambiguo=amb, motivo=mot))
            n += 1
        print(vid, n, "frames", flush=True)
    df = pd.DataFrame(linhas)
    df.to_csv(MAN, index=False)
    ok = df[df.imagem.notna()]
    print(pd.crosstab([ok.video, ok.ambiguo], [ok.dia, ok.classe.fillna("?")]))
    print(df.motivo.value_counts().to_string())


if __name__ == "__main__":
    main()
