#!/usr/bin/env python3
"""Modo demonstração: reproduz uma sessão gravada como se o carro estivesse rodando AGORA.

Para a defesa: o sistema funciona na frente da banca sem depender de chover. Lê
pares ``frame_*.jpg`` + ``.json`` de uma sessão real (com GPS) e, a cada
``--intervalo`` segundos, deposita um par NOVO na fila da câmera (``~/frames``),
com ``capturado_em_utc`` = agora e a posição GPS original. Daí em diante é o
pipeline de verdade: ``uploader.service`` -> gate -> ``/api/v1/ingest`` -> modelo
no backend -> dashboard ao vivo.

``--decisao``:
  - ``gate`` (padrão): o gate da placa decide chuva/seco, como em produção;
  - ``estacao``: usa o rótulo de estação gravado no JSON de origem
    (``rotulo_estacao``) — para mostrar o fluxo completo mesmo onde o gate atual
    deixaria a chuva passar despercebida (limitação documentada do gate).

Compatível com o Python 3.6 da Jetson (só stdlib).

Uso (na Jetson):
    python3 demo_replay.py --origem /home/jetson/demo/sessao_2309 --intervalo 2
"""

import argparse
import glob
import json
import os
import shutil
import time
from datetime import datetime, timezone

FILA = "/home/jetson/frames"


def _escrever_atomico(caminho, dados, binario):
    tmp = caminho + ".tmp"
    with open(tmp, "wb" if binario else "w") as f:
        f.write(dados)
    os.replace(tmp, caminho)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origem", required=True)
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--decisao", choices=("gate", "estacao"), default="gate")
    ap.add_argument("--fila", default=FILA)
    args = ap.parse_args()

    jsons = sorted(glob.glob(os.path.join(args.origem, "frame_*.json")))
    print("[demo] %d frames de %s, 1 a cada %.1f s, decisão: %s" % (len(jsons), args.origem, args.intervalo, args.decisao), flush=True)
    for i, js in enumerate(jsons):
        with open(js) as f:
            orig = json.load(f)
        agora = datetime.now(timezone.utc)
        nome = "frame_%s_%03d" % (agora.strftime("%Y%m%d_%H%M%S"), agora.microsecond // 1000)
        iso = agora.isoformat()
        gps = dict(orig.get("gps") or {})
        gps.update({"fix": True, "ultimo_fix_em": iso})
        meta = {"schema": 2, "device_id": orig.get("device_id", "jetson-nano-01"), "capturado_em_utc": iso,
                "arquivo": nome + ".jpg", "gps": gps,
                "demo": {"origem": os.path.basename(js), "capturado_originalmente": orig.get("capturado_em_utc")}}
        if args.decisao == "estacao" and orig.get("rotulo_estacao"):
            meta["weather_label"] = "chuva" if orig["rotulo_estacao"] != "seco" else "seco"
            meta["confidence"] = 1.0
        # mesmo contrato da captura: o .json só aparece depois do .jpg completo
        with open(js[:-5] + ".jpg", "rb") as f:
            _escrever_atomico(os.path.join(args.fila, nome + ".jpg"), f.read(), True)
        _escrever_atomico(os.path.join(args.fila, nome + ".json"), json.dumps(meta), False)
        print("[demo] %d/%d %s (%s)" % (i + 1, len(jsons), nome, os.path.basename(js)), flush=True)
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
