"""Etapa 7: procura chuva moderada/forte pelo radar nos vídeos que o BDD NÃO marcou como rainy.

O rótulo de tempo do BDD é visual e grosseiro: 'overcast', 'undefined', 'partly cloudy' e 'foggy'
podem ter chuva no radar. Triagem barata: só t0 para todos; quem tem >= moderada no ponto ganha
t0 ±2 e ±4 min para a regra de ambiguidade. Reaproveita as etapas 2 e 4 com outra pasta de estado
(data/raw/public_datasets/bdd100k/amplo/) e grava data/manifests/bdd_mrms_amplo.csv, que a
etapa 6 consome:  .venv/bin/python scripts/bdd/etapa6_frames_video.py data/manifests/bdd_mrms_amplo.csv \
                     data/manifests/bdd_mrms_amplo_frames.csv
Retoma sozinho (pula JSON de info e timestamp de radar já lidos).
"""
import json, sys, time, zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from nucleo import timestamp_mrms_mais_proximo, url_mrms, mrms_valido, LIMIAR_GAROA
import mrms, etapa2_gps, etapa4_rotular

D = Path("data/raw/public_datasets/bdd100k")
D2 = D / "amplo"; D2.mkdir(exist_ok=True)
SAIDA = D2 / "mrms_janelas.json"
TEMPOS = {"overcast", "undefined", "partly cloudy", "foggy"}


def selecionar():
    if (D2 / "selecao.json").exists():
        return
    z = zipfile.ZipFile(D / "labels.zip")
    rows = []
    for n in z.namelist():
        if not n.endswith(".json") or "/test/" in n:
            continue
        j = json.loads(z.read(n)); a = j.get("attributes", {})
        if a.get("weather") in TEMPOS:
            rows.append(dict(name=j["name"], split=n.split("/")[1], weather=a.get("weather"),
                             scene=a.get("scene"), timeofday=a.get("timeofday")))
    (D2 / "selecao.json").write_text(json.dumps(rows))
    print(len(rows), "vídeos selecionados", flush=True)


def rodar(pedidos, estado):
    """Como a etapa 3, mas pula só o que já foi lido PARA AQUELE vídeo (o mesmo timestamp pode
    servir a vídeos diferentes em fases diferentes)."""
    todo = {t: p for t, p in pedidos.items()
            if estado.get(t) != "ERRO" and not all(n in (estado.get(t) or {}) for n, _, _ in p)}
    print(f"{len(todo)} arquivos a baixar", flush=True)

    def um(item):
        t, ps = item
        time.sleep(0.1)
        b = mrms.baixar(url_mrms(datetime.fromisoformat(t)))
        if b is None:
            return t, None
        v = mrms.campo(b)
        return t, {n: mrms.janela3x3(v, i, j) for n, i, j in ps}

    feitos = 0
    with ThreadPoolExecutor(10) as ex:
        for t, r in ex.map(um, todo.items()):
            if r is None:
                estado[t] = "ERRO"
            else:
                estado[t] = {**(estado.get(t) or {}), **r}
            feitos += 1
            if feitos % 200 == 0:
                SAIDA.write_text(json.dumps(estado)); print(feitos, flush=True)
    SAIDA.write_text(json.dumps(estado))


def montar(amostras, offsets):
    ped = defaultdict(list)
    for a in amostras:
        for o in offsets:
            ped[(datetime.fromisoformat(a["ts0"]) + timedelta(minutes=o)).isoformat()].append((a["name"], *a["_ij"]))
    return ped


def main():
    selecionar()
    if not (D2 / "selecao_gps.json").exists():
        etapa2_gps.D = D2
        etapa2_gps.main()
    sel = [r for r in json.loads((D2 / "selecao_gps.json").read_text()) if "lat" in r and not r.get("timelapse")]
    for a in sel:
        a["ts0"] = timestamp_mrms_mais_proximo(datetime.fromtimestamp(a["utc_ms"] / 1000, timezone.utc)).isoformat()
        a["_ij"] = mrms.indice(a["lat"], a["lon"])
    sel = [a for a in sel if a["_ij"] is not None]
    print(len(sel), "vídeos com GPS dentro da grade do MRMS", flush=True)
    estado = json.loads(SAIDA.read_text()) if SAIDA.exists() else {}

    rodar(montar(sel, (0,)), estado)

    def centro(a):
        d = estado.get(a["ts0"])
        d = d.get(a["name"]) if isinstance(d, dict) else None
        return mrms_valido(d[4]) if d else None
    cand = [a for a in sel if (centro(a) or 0) > LIMIAR_GAROA]
    print(len(cand), "candidatos >= moderada em t0 -> ±2, ±4 min", flush=True)
    rodar(montar(cand, (-2, 2, -4, 4)), estado)

    etapa4_rotular.D = D2
    etapa4_rotular.OUT = Path("data/manifests/bdd_mrms_amplo.csv")
    etapa4_rotular.main()


if __name__ == "__main__":
    main()
