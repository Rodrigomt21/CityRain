"""Limpeza dos frames das câmeras veiculares (dashcam_radar.py) antes do treino.

Duas exclusões, nenhuma muda classe (o rótulo continua sendo o do radar):
- legenda: texto que o autor do vídeo sobrepôs à imagem (ex.: "Believe it if you need it." no
  derecho de Houston) -> atalho "tem texto = forte". OCR na faixa de baixo; >= 8 letras = descarta.
  Só nos vídeos com legenda do autor (VIDEOS_COM_LEGENDA): em geral o OCR acha texto da cena (traseira de
  caminhão, placas), que é natural e fica.
- quase_duplicado: carro parado (Rockford, sob o viaduto) gera frames iguais; dentro de cada vídeo,
  frame cuja diferença média para o último frame mantido é < LIMIAR_DIF (0-255, em 64x48 cinza) sai.

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_youtube/limpar_dashcam.py
Grava a coluna `usar` e `exclusao` em data/manifests/dashcam_eua_mrms.csv e um painel dos excluídos.
"""
import re, subprocess, tempfile
from pathlib import Path
import numpy as np, pandas as pd
from PIL import Image, ImageDraw

MAN = Path("data/manifests/dashcam_eua_mrms.csv")
FR = Path("data/processed/youtube/dashcam_eua")
LIMIAR_DIF = 3.0
VIDEOS_COM_LEGENDA = {"BEl8JZr-NHY"}


def tem_legenda(img: Image.Image) -> bool:
    w, h = img.size
    faixa = img.crop((0, int(h * 0.62), w, int(h * 0.97))).convert("L")
    faixa = faixa.resize((faixa.width * 2, faixa.height * 2))
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        faixa.save(f.name)
        txt = subprocess.run(["tesseract", f.name, "-", "--psm", "6"], capture_output=True, text=True).stdout
    # legenda = palavras de verdade; ruído de OCR em chuva vira símbolos soltos
    palavras = [p for p in re.findall(r"[A-Za-z]{3,}", txt)]
    return sum(len(p) for p in palavras) >= 8


def main():
    df = pd.read_csv(MAN)
    df["usar"], df["exclusao"] = False, ""
    base = df.imagem.notna() & df.dia.fillna(False).astype(bool) & ~df.ambiguo.fillna(True).astype(bool)
    for vid, g in df[base].groupby("video"):
        ultimo = None
        for i, r in g.sort_values("seg").iterrows():
            img = Image.open(FR / r.imagem).convert("RGB")
            if vid in VIDEOS_COM_LEGENDA and tem_legenda(img):
                df.loc[i, "exclusao"] = "legenda"; continue
            mini = np.asarray(img.convert("L").resize((64, 48)), dtype=np.float32)
            if ultimo is not None and np.abs(mini - ultimo).mean() < LIMIAR_DIF:
                df.loc[i, "exclusao"] = "quase_duplicado"; continue
            ultimo = mini
            df.loc[i, "usar"] = True
    df.to_csv(MAN, index=False)
    b = df[base]
    print(pd.crosstab([b.video, b.classe], b.exclusao.replace("", "usa")))
    ex = b[b.exclusao != ""].sample(min(18, (b.exclusao != "").sum()), random_state=0)
    c = Image.new("RGB", (6 * 320, 3 * 240))
    for k, r in enumerate(ex.itertuples()):
        im = Image.open(FR / r.imagem).resize((320, 240)); ImageDraw.Draw(im).text((4, 4), f"{r.exclusao} {r.video[:6]}", fill="yellow")
        c.paste(im, ((k % 6) * 320, (k // 6) * 240))
    c.save("data/review/dashcam_eua_excluidos.jpg", quality=85)


if __name__ == "__main__":
    main()
