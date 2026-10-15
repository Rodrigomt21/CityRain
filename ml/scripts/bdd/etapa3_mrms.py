"""Etapa 3: para cada amostra com GPS, lê MRMS (3x3) em t0, ±2, ±4 e (se seco) ±6, ±10 min."""
import json, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from nucleo import timestamp_mrms_mais_proximo, url_mrms
import mrms

D = Path("data/raw/public_datasets/bdd100k")
SAIDA = D / "mrms_janelas.json"   # {ts: {nome: [9 valores] | null}}  ts ausente/ "ERRO" = arquivo 404


def rodar(pedidos, estado):
    """pedidos: {ts_iso: [(nome,i,j)]}."""
    todo = {t: p for t, p in pedidos.items() if t not in estado}
    print(f"{len(todo)} arquivos a baixar", flush=True)

    def um(item):
        t, ps = item
        ts = datetime.fromisoformat(t)
        time.sleep(0.1)
        b = mrms.baixar(url_mrms(ts))
        if b is None:
            return t, None
        v = mrms.campo(b)
        return t, {n: mrms.janela3x3(v, i, j) for n, i, j in ps}

    feitos = 0
    with ThreadPoolExecutor(10) as ex:
        for t, r in ex.map(um, todo.items()):
            estado[t] = r if r is not None else "ERRO"
            feitos += 1
            if feitos % 100 == 0:
                SAIDA.write_text(json.dumps(estado)); print(feitos, flush=True)
    SAIDA.write_text(json.dumps(estado))


def montar(amostras, offsets):
    ped = defaultdict(list)
    for a in amostras:
        a_ts = timestamp_mrms_mais_proximo(datetime.fromtimestamp(a["utc_ms"] / 1000, timezone.utc))
        a["ts0"] = a_ts.isoformat()
        idx = mrms.indice(a["lat"], a["lon"])
        if idx is None:
            a["motivo_descarte"] = "fora_da_grade"; continue
        a["_ij"] = idx
        for o in offsets(a):
            ped[(a_ts + timedelta(minutes=o)).isoformat()].append((a["name"], *idx))
    return ped


def main():
    sel = [r for r in json.loads((D / "selecao_gps.json").read_text()) if "lat" in r and not r.get("timelapse")]
    print(len(sel), "amostras com GPS (sem timelapse)")
    estado = json.loads(SAIDA.read_text()) if SAIDA.exists() else {}
    def centro(a, off=0):
        d = estado.get((datetime.fromisoformat(a["ts0"]) + timedelta(minutes=off)).isoformat())
        d = d.get(a["name"]) if isinstance(d, dict) else None
        return d[4] if d else None

    rodar(montar(sel, lambda a: (0, -2, 2)), estado)
    # fase 2: chuva (>0 no ponto em t0) precisa de ±4; seco precisa de ±4, ±6, ±10 (regra de seco)
    prox = [a for a in sel if "_ij" in a and centro(a) is not None]
    chuva = [a for a in prox if centro(a) > 0]
    secos = [a for a in prox if centro(a) == 0]
    print(len(chuva), "com chuva;", len(secos), "secos -> fase 2")
    rodar(montar(chuva, lambda a: (-4, 4)), estado)
    rodar(montar(secos, lambda a: (-4, 4, -6, 6, -10, 10)), estado)


if __name__ == "__main__":
    main()
