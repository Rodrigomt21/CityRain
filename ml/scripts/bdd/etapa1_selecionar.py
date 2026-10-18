"""Etapa 1: lê bdd100k_labels.zip e seleciona imagens rainy e amostra de clear."""
import json, random, zipfile, sys
from collections import Counter
from pathlib import Path

D = Path("data/raw/public_datasets/bdd100k")

def main():
    z = zipfile.ZipFile(D / "labels.zip")
    rows = []
    for n in z.namelist():
        if not n.endswith(".json") or "/test/" in n:
            continue
        split = n.split("/")[1]
        j = json.loads(z.read(n))
        a = j.get("attributes", {})
        rows.append(dict(name=j["name"], split=split, weather=a.get("weather"),
                         scene=a.get("scene"), timeofday=a.get("timeofday")))
    c = Counter((r["weather"], r["timeofday"]) for r in rows)
    print(len(rows), c.most_common())
    rain = [r for r in rows if r["weather"] == "rainy"]
    clear = [r for r in rows if r["weather"] == "clear"]
    random.Random(0).shuffle(clear)
    sel = rain + clear[:3000]
    (D / "selecao.json").write_text(json.dumps(sel))
    print("rainy", len(rain), "clear amostra", len(sel) - len(rain))

if __name__ == "__main__":
    main()
