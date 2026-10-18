"""Monta ml/data/splits/intensidade_v9_mapillary.csv = v8 (carro + irCNN + BDD + dashcam, só dia) + fotos de
para-brisa do Mapillary rotuladas por radar MRMS (baixar_mapillary.py, `usar` = True).

Tudo do Mapillary vai para 'train' (origem 'mapillary', evento_id = área + dia UTC); o teste continua irCNN
+ carro + YouTube ordinal.

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/montar_split_v9.py
"""
from pathlib import Path
import pandas as pd

BASE = Path("data/splits/intensidade_v8_dashcam.csv")
OUT = Path("data/splits/intensidade_v9_mapillary.csv")
AREAS = ["jacksonville"]


def main():
    novos = []
    for area in AREAS:
        d = pd.read_csv(f"data/manifests/mapillary_{area}.csv")
        d = d[d.usar.fillna(False).astype(bool)]
        novos.append(pd.DataFrame(dict(caminho="ml/data/processed/mapillary/" + d.imagem, classe=d.classe, mm_h=d.mm_h,
                                       particao="train", origem="mapillary",
                                       evento_id=f"mapillary__{area}_" + d.utc.str[:10], periodo="dia")))
    novo = pd.concat(novos, ignore_index=True)
    out = pd.concat([pd.read_csv(BASE), novo], ignore_index=True)
    out.to_csv(OUT, index=False)
    print(OUT, len(out), "linhas")
    print(novo.groupby(["evento_id", "classe"]).size())


if __name__ == "__main__":
    main()
