"""Marca frames de para-brisa com rótulo de radar suspeito (versão simples de "confident learning").

Usa as predições FORA DO FOLD (``predicoes_test_parabrisa.csv`` das CVs com ``parabrisa_cv``): cada frame foi
previsto por modelos que nunca viram o dia dele. Suspeito = TODOS os modelos dão probabilidade < LIMIAR à classe
do radar. Esses frames saem só do TREINO (``dados.excluir_treino_csv``); a nota de para-brisa continua medida
em todos os frames, então a limpeza não maquia o teste.

Uso (de dentro de ml/):
    .venv/bin/python scripts/avaliacao/marcar_rotulo_suspeito.py v13_pb20 v14a_foto --saida data/splits/suspeitos_pb.csv
"""
import argparse
import glob

import pandas as pd

LIMIAR = 0.10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cvs", nargs="+", help="sufixos das CVs, ex.: v13_pb20")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--limiar", type=float, default=LIMIAR)
    a = ap.parse_args()
    p_rotulo = []
    for v in a.cvs:
        d = pd.concat([pd.read_csv(f) for f in glob.glob(f"runs/intensidade_cv_{v}_dia_mnv3_fold*/predicoes_test_parabrisa.csv")])
        p_rotulo.append(d.apply(lambda r: r[f"p_{r.classe}"], axis=1).rename(v).set_axis(d.caminho))
    m = pd.concat(p_rotulo, axis=1)
    info = d.drop_duplicates("caminho").set_index("caminho")[["classe", "mm_h", "evento_id"]]
    sus = info.loc[(m < a.limiar).all(axis=1)].reset_index()
    sus.to_csv(a.saida, index=False)
    print(f"{len(sus)} de {len(m)} frames suspeitos ({len(sus) / len(m):.1%}) -> {a.saida}")
    print(pd.crosstab(sus.evento_id, sus.classe))


if __name__ == "__main__":
    main()
