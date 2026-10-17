"""Monta ml/data/splits/intensidade_v16_pb27.csv = v13 + 7 dias de para-brisa revisados em 17/10 à tarde
(schok, vorpalblade, directionup, whitecotton, jacklehoullier; ver DATAS em baixar_mapillary.py): 20 -> 27 eventos.
Mesma regra da v13 (teto de 300 fotos por evento e classe, tudo em 'train').

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/montar_split_v16.py
"""
from pathlib import Path
import montar_split_v13 as v13

v13.BASE = Path("data/splits/intensidade_v13_pb20.csv")
v13.OUT = Path("data/splits/intensidade_v16_pb27.csv")
v13.FONTES = {f"criador_{u}": u for u in ("schok", "vorpalblade", "directionup", "whitecotton", "jacklehoullier")}

if __name__ == "__main__":
    v13.main()
