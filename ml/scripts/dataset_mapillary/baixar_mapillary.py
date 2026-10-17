"""Baixa as fotos de chuva do Mapillary já rotuladas pelo radar (candidatas.csv de mapillary_chuva.py).

Só dia, rótulo inequívoco, classes de chuva e as datas aprovadas em revisão visual (DATAS: o
captured_at foi conferido contra o relógio da câmera e a chegada da chuva no radar). Por sequência,
1 foto a cada PASSO_S segundos; tira a faixa de texto de baixo (BlackVue grava data/velocidade),
recorte central 4:3 e descarta quase duplicados (mesma regra de limpar_dashcam.py).

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/baixar_mapillary.py jacksonville
Saída: data/processed/mapillary/<area>/*.jpg e data/manifests/mapillary_<area>.csv
"""
import io, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd, requests
from PIL import Image

# área -> datas UTC revisadas (Jacksonville 27/07/2024: relógio BlackVue 11 h fora, minutos batem;
# asfalto seco até 20:39, chuva a partir de 20:48, radar 0 -> 78 mm/h às 20:50)
DATAS = {"jacksonville": ["2024-07-27"],
         # usuário 'allen' (mapillary_criador.py), BlackVue DR900X no para-brisa; painéis data/review/allen_*.jpg.
         # Relógio da câmera: 11 h fora em 2024, EDT a partir de 2025 (minutos batem com o Mapillary nos dois).
         # Fora: GoPro/Garmin pela janela lateral ou sacada (2022-11-10, 2023-*, 2024-07-20, 2024-08-04,
         # 2026-04-07) e inverno com neve no chão (2024-12-27, 2025-01-19: o radar pode estar medindo neve).
         "criador_allen": ["2024-07-27", "2024-09-09", "2025-07-09", "2025-08-23", "2025-08-24", "2026-04-05",
                           "2026-05-29"],
         # Savannah 25/08/2023: BlackVue DR590W no para-brisa; relógio 11 h fora, minutos e segundos batem;
         # chuva forte visível nas 8 sequências (radar 14-87 mm/h). NY 04/07/2023 fora: GoPro em carro parado, vidro seco.
         "savannah": ["2023-08-25"],
         # usuário 'cubanoboi' (Flórida), iPhone por dentro do para-brisa (limpador/gotas/capô à vista); hora do
         # celular (GPS), sem desvio de relógio. Fora: 2025-11-27 (foto pela janela lateral), 2025-06-03 (não revisado).
         "criador_cubanoboi": ["2025-06-10", "2025-07-13", "2025-07-14", "2025-08-08", "2025-08-22", "2026-08-29"],
         # usuário 'Satsuka_Osaka' (EUA), iPhone por dentro do para-brisa, limpador visível
         "criador_Satsuka_Osaka": ["2026-04-25"]}
# câmera aceita por fonte (o BlackVue do allen sobe com make "none" ou "BlackVue"); sem entrada = qualquer câmera
CAMERAS = {"criador_allen": {"none", "BlackVue"}, "savannah": {"none", "BlackVue"},
           "criador_cubanoboi": {"Apple"}, "criador_Satsuka_Osaka": {"Apple"}}
PASSO_S = 2
FAIXA_TEXTO = 0.05
LIMIAR_DIF = 3.0
TOKEN = re.search(r"MAPILLARY_TOKEN=(\S+)", Path(".env").read_text()).group(1)


def baixar(id_):
    j = requests.get(f"https://graph.mapillary.com/{id_}", timeout=60,
                     params=dict(access_token=TOKEN, fields="thumb_1024_url,make,model")).json()
    img = Image.open(io.BytesIO(requests.get(j["thumb_1024_url"], timeout=60).content)).convert("RGB")
    return img, j.get("make") or "", j.get("model") or ""


def main():
    area = sys.argv[1]
    out = Path(f"data/processed/mapillary/{area}"); out.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(f"data/raw/public_datasets/mapillary/{area}/candidatas.csv")
    d = d[d.dia & ~d.ambiguo & d.classe.isin(["garoa", "moderada", "forte"]) & d.utc.str[:10].isin(DATAS[area])].copy()
    d["t"] = pd.to_datetime(d.utc, format="ISO8601")
    d = d.sort_values("t").assign(b=d.t.dt.floor(f"{PASSO_S}s")).drop_duplicates(["seq", "b"])
    print(len(d), "fotos após 1 a cada", PASSO_S, "s por sequência", flush=True)

    def um(r):
        try:
            img, make, model = baixar(r.id)
        except Exception as e:  # foto removida do Mapillary etc.
            return dict(id=r.id, erro=str(e)[:80])
        w, h = img.size
        img = img.crop((0, 0, w, int(h * (1 - FAIXA_TEXTO))))
        w, h = img.size
        cw = min(w, round(h * 4 / 3)); x0 = (w - cw) // 2
        img = img.crop((x0, 0, x0 + cw, h))
        nome = f"{r.id}.jpg"; img.save(out / nome, quality=92)
        return dict(id=r.id, imagem=f"{area}/{nome}", make=make, model=model)
    with ThreadPoolExecutor(8) as ex:
        info = pd.DataFrame(list(ex.map(um, d.itertuples())))
    d = d.merge(info, on="id")
    d["usar"], d["exclusao"] = d.imagem.notna(), np.where(d.imagem.isna(), "erro_download", "")
    if area in CAMERAS:
        fora = d.usar & ~d.make.isin(CAMERAS[area])
        d.loc[fora, ["usar", "exclusao"]] = [False, "outra_camera"]
    for _, g in d[d.usar].groupby("seq"):
        ultimo = None
        for i, r in g.sort_values("t").iterrows():
            mini = np.asarray(Image.open(out.parent / r.imagem).convert("L").resize((64, 48)), dtype=np.float32)
            if ultimo is not None and np.abs(mini - ultimo).mean() < LIMIAR_DIF:
                d.loc[i, ["usar", "exclusao"]] = [False, "quase_duplicado"]; continue
            ultimo = mini
    d.drop(columns=["t", "b"]).to_csv(f"data/manifests/mapillary_{area}.csv", index=False)
    print(pd.crosstab([d.make, d.classe], d.exclusao.replace("", "usa")))


if __name__ == "__main__":
    main()
