"""Monta ml/data/splits/intensidade_v13_pb20.csv = v10 + mais para-brisa do Mapillary (12 -> 20 eventos):
'cubanoboi' (iPhone, Flórida, 6 dias), 'Satsuka_Osaka' (iPhone, 1 dia) e BlackVue de Savannah 25/08/2023 (busca
por área). Motivo: a CV v11 mostrou que o modelo não generaliza entre dias de para-brisa (Spearman por evento
-0,19); o que falta são dias diferentes, não fotos do mesmo dia.

Teto de TETO fotos por (evento, classe), igualmente espaçadas no tempo, para nenhum dia dominar o treino.
Tudo novo vai para 'train'; evento_id = fonte + dia UTC.

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/montar_split_v13.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("data/splits/intensidade_v10_allen.csv")
OUT = Path("data/splits/intensidade_v13_pb20.csv")
CLASSES = ["garoa", "moderada", "forte"]
TETO = 300
FONTES = {"criador_cubanoboi": "cubanoboi", "criador_Satsuka_Osaka": "satsuka", "savannah": "savannah"}


def main():
    partes = []
    for area, nome in FONTES.items():
        mp = pd.read_csv(f"data/manifests/mapillary_{area}.csv")
        mp = mp[mp.usar.fillna(False).astype(bool) & mp.classe.isin(CLASSES)].sort_values("utc")
        mp["evento_id"] = f"mapillary__{nome}_" + mp.utc.str[:10]
        for _, g in mp.groupby(["evento_id", "classe"]):
            partes.append(g.iloc[np.unique(np.linspace(0, len(g) - 1, min(TETO, len(g))).round().astype(int))])
    mp = pd.concat(partes, ignore_index=True)
    novo = pd.DataFrame(dict(caminho="ml/data/processed/mapillary/" + mp.imagem, classe=mp.classe, mm_h=mp.mm_h,
                             particao="train", origem="mapillary", evento_id=mp.evento_id, periodo="dia"))
    out = pd.concat([pd.read_csv(BASE), novo], ignore_index=True)
    out.to_csv(OUT, index=False)
    print(OUT, len(out), "linhas")
    print(pd.crosstab(novo.evento_id, novo.classe))


if __name__ == "__main__":
    main()
