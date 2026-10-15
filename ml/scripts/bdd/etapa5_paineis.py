"""Etapa 5: puxa (remotezip) as imagens inequívocas e monta painéis de 24 miniaturas por classe."""
import random, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw
from remotezip import RemoteZip

D = Path("data/raw/public_datasets/bdd100k")
IMG = D / "imagens"; IMG.mkdir(exist_ok=True)
URL = "http://dl.yf.io/bdd100k/bdd100k_images_100k.zip"
REV = Path("data/review/bdd_mrms"); REV.mkdir(parents=True, exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24


def baixar(lote):
    rz = RemoteZip(URL)
    for _, r in lote:
        d = IMG / r.imagem
        if not d.exists():
            d.write_bytes(rz.read(f"bdd100k/images/100k/{r.split}/{r.imagem}"))


def painel(df, nome, k=N, seed=0):
    g = df.sample(min(k, len(df)), random_state=seed)
    W, H, cols = 320, 180, 6
    rows = (len(g) + cols - 1) // cols
    im = Image.new("RGB", (cols * W, rows * H), "black")
    for n, (_, r) in enumerate(g.iterrows()):
        t = Image.open(IMG / r.imagem).convert("RGB").resize((W, H))
        ImageDraw.Draw(t).text((4, 4), f"{r.mm_ponto:.1f}mm/h {r.timeofday[:5]} {r.weather_bdd}", fill="yellow")
        im.paste(t, ((n % cols) * W, (n // cols) * H))
    im.save(REV / nome, quality=85)


def main():
    df = pd.read_csv("data/manifests/bdd_mrms.csv")
    ok = df[(~df.ambiguo) & (df.classe.notna())]
    # baixa só o necessário: amostra por classe x conjunto (painéis) para economizar banda
    pedidos = []
    for (conj, c), g in ok.assign(conj=ok.weather_bdd.eq("rainy")).groupby(["conj", "classe"]):
        pedidos.append(g.sample(min(len(g), 3 * N), random_state=1))
    pedidos = pd.concat(pedidos)
    itens = list(pedidos.iterrows())
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(baixar, [itens[i::4] for i in range(4)]))
    for (conj, c), g in ok.assign(conj=ok.weather_bdd.eq("rainy")).groupby(["conj", "classe"]):
        g = g[g.imagem.map(lambda x: (IMG / x).exists())]
        for per, gg in (("dia", g[g.timeofday == "daytime"]), ("noite", g[g.timeofday == "night"])):
            if len(gg):
                painel(gg, f"{'rainy' if conj else 'clear'}_{c}_{per}.jpg")
    print(sorted(p.name for p in REV.iterdir()))


if __name__ == "__main__":
    main()
