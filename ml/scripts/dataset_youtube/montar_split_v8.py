"""Monta ml/data/splits/intensidade_v8_dashcam.csv = v7 (carro + irCNN + BDD de dia) + câmeras veiculares
do YouTube (EUA, radar MRMS) com `usar` = True (limpar_dashcam.py): forte de para-brisa de dia.

Tudo do dashcam vai para 'train' (origem 'dashcam', evento_id = vídeo); o teste continua irCNN + carro +
YouTube ordinal. Rodar antes: dashcam_radar.py e limpar_dashcam.py.

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_youtube/montar_split_v8.py
"""
from pathlib import Path
import pandas as pd

BASE = Path("data/splits/intensidade_v7_bdd.csv")
OUT = Path("data/splits/intensidade_v8_dashcam.csv")
MAN = Path("data/manifests/dashcam_eua_mrms.csv")


def main():
    d = pd.read_csv(MAN)
    d = d[d.usar.fillna(False).astype(bool) & d.classe.isin(["garoa", "moderada", "forte"])]
    novo = pd.DataFrame(dict(caminho="ml/data/processed/youtube/dashcam_eua/" + d.imagem, classe=d.classe,
                             mm_h=d.mm_h, particao="train", origem="dashcam", evento_id="dashcam__" + d.video,
                             periodo="dia"))
    out = pd.concat([pd.read_csv(BASE), novo], ignore_index=True)
    out.to_csv(OUT, index=False)
    print(OUT, len(out), "linhas")
    print(novo.groupby(["evento_id", "classe"]).size())


if __name__ == "__main__":
    main()
