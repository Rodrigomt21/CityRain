"""Monta ml/data/splits/intensidade_v7_bdd.csv = intensidade_v1.csv + BDD100K (radar MRMS) no treino.

Só DIA (timeofday == daytime; noite e amanhecer/entardecer ficam fora do escopo do modelo do carro)
e só rótulos inequívocos. Tudo vem de frames de vídeo (etapa 6), inclusive a garoa, para a fonte
da imagem não virar atalho: moderada/forte de bdd_mrms_frames.csv (+ bdd_mrms_amplo_frames.csv) e
garoa de bdd_mrms_garoa_frames.csv (amostra de 300 vídeos), sem o que o BDD viraria "cara de moderada".
Todo o BDD vai para 'train' (origem 'bdd', evento_id = vídeo): o teste continua irCNN + carro.

O BDD é 16:9 (1280x720) e o carro 4:3 (640x480): o resize do treino achataria o BDD (atalho visual).
Por isso cada frame é recortado no centro para 4:3 (960x720) em frames_video_43/.

Uso (de dentro de ml/): .venv/bin/python scripts/bdd/montar_split_v7.py
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
from PIL import Image

ORIG = Path("data/raw/public_datasets/bdd100k/frames_video")
DEST = Path("data/raw/public_datasets/bdd100k/frames_video_43"); DEST.mkdir(exist_ok=True)
FR = "ml/" + str(DEST) + "/"
BASE = Path("data/splits/intensidade_v1.csv")
OUT = Path("data/splits/intensidade_v7_bdd.csv")
FRAMES = ["bdd_mrms_frames.csv", "bdd_mrms_amplo_frames.csv", "bdd_mrms_garoa_frames.csv"]


def recortar_43(nome: str) -> None:
    """Recorte central 4:3 (mesma proporção da câmera do carro)."""
    d = DEST / nome
    if d.exists():
        return
    im = Image.open(ORIG / nome)
    w, h = im.size
    cw = min(w, round(h * 4 / 3))
    x0 = (w - cw) // 2
    im.crop((x0, 0, x0 + cw, h)).save(d, quality=95)


def main():
    base = pd.read_csv(BASE)
    fr = pd.concat([pd.read_csv(p) for p in (Path("data/manifests") / n for n in FRAMES) if p.exists()],
                   ignore_index=True)
    fr = fr[(~fr.ambiguo) & (fr.timeofday == "daytime")].drop_duplicates(subset=["imagem"])
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(recortar_43, fr.imagem))
    bdd = pd.DataFrame(dict(caminho=FR + fr.imagem, classe=fr.classe, mm_h=fr.mm_ponto,
                            particao="train", origem="bdd", evento_id="bdd__" + fr.video, periodo="dia"))
    out = pd.concat([base, bdd], ignore_index=True)
    out.to_csv(OUT, index=False)
    print(OUT, len(out), "linhas")
    print(bdd.groupby("classe").agg(frames=("caminho", "size"), videos=("evento_id", "nunique")))


if __name__ == "__main__":
    main()
