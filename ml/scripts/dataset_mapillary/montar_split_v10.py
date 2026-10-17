"""Monta ml/data/splits/intensidade_v10_allen.csv = v7 (carro + irCNN + BDD de dia) + câmeras veiculares do YouTube
(`usar` em dashcam_eua_mrms.csv, agora com Los Angeles 17/02/2017) + BlackVue de para-brisa do usuário 'allen' no
Mapillary (7 dias revisados, forte/moderada/garoa; inclui o 27/07/2024 que na v9 veio da busca por área).

Tudo novo vai para 'train'; evento_id = vídeo ou dia UTC. O teste continua irCNN + carro + YouTube ordinal.

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/montar_split_v10.py
"""
from pathlib import Path
import pandas as pd

BASE = Path("data/splits/intensidade_v7_bdd.csv")
OUT = Path("data/splits/intensidade_v10_allen.csv")
CLASSES = ["garoa", "moderada", "forte"]


def main():
    dc = pd.read_csv("data/manifests/dashcam_eua_mrms.csv")
    dc = dc[dc.usar.fillna(False).astype(bool) & dc.classe.isin(CLASSES)]
    dc = pd.DataFrame(dict(caminho="ml/data/processed/youtube/dashcam_eua/" + dc.imagem, classe=dc.classe, mm_h=dc.mm_h,
                           particao="train", origem="dashcam", evento_id="dashcam__" + dc.video, periodo="dia"))
    mp = pd.read_csv("data/manifests/mapillary_criador_allen.csv")
    mp = mp[mp.usar.fillna(False).astype(bool)]
    mp = pd.DataFrame(dict(caminho="ml/data/processed/mapillary/" + mp.imagem, classe=mp.classe, mm_h=mp.mm_h,
                           particao="train", origem="mapillary", evento_id="mapillary__allen_" + mp.utc.str[:10],
                           periodo="dia"))
    novo = pd.concat([dc, mp], ignore_index=True)
    out = pd.concat([pd.read_csv(BASE), novo], ignore_index=True)
    out.to_csv(OUT, index=False)
    print(OUT, len(out), "linhas")
    print(novo.groupby(["origem", "classe"]).size())


if __name__ == "__main__":
    main()
