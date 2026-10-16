"""Baixa a série CEMADEN do dia de cada vídeo do YouTube (carro na chuva, data e local no título).

Só os pluviômetros mais próximos do trajeto (a cota do PED é do cadastro: poucas chamadas).
Imprime, por vídeo, os eventos de chuva do dia (mm/h em janelas de 10 min, horário de Brasília)
para casar com o vídeo: só entra no treino o dia com UM evento claro (ver docs/retomada-bdd100k-15out.md).

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_youtube/cemaden_videos_forte.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "estacoes"))
import baixar_cemaden_ped as ped

# vídeo -> (dia local, estações perto do trajeto: código -> nome)
VIDEOS = {
    "qcI7SWTst4I": ("2023-03-10", {"355030833A": "AC Central de SP", "355030826A": "Mooca",
                                   "355030853A": "Pinheiros", "355030877A": "Vila Formosa"}),
    "w8YYa2fA1zk": ("2020-11-11", {"355030859A": "Vila Aricanduva", "355030806B": "Cidade Líder",
                                   "355030849A": "Vila Carrão"}),
    "UQ93-WJEii0": ("2020-10-30", {"355030833A": "AC Central de SP", "355030857A": "Centro"}),
    "3oJJvBDv2Fc": ("2023-10-04", {"352230703A": "Rio Branco (Itapetininga)", "352230701A": "Centro (Itapetininga)"}),
    "eMbR-ksmE7M": ("2019-03-08", {"350950202A": "Barão Geraldo", "350950205A": "Sousas"}),
    "1qMskjMVVdI": ("2021-01-02", {"355620601A": "Vila São Sebastião (Valinhos)", "350950202A": "Barão Geraldo"}),
}


def serie(cod: str, dia: str) -> list[tuple[datetime, float]]:
    """(hora local, mm) por leitura. O PED devolve texto ';' em UTC, com leitura a cada 1 h
    quando seco e a cada 10 min quando chove."""
    p = ped.RAW_DIR / f"dados_pcd_{cod}_{dia}.json"
    if not p.exists():
        return []
    out = []
    for ln in p.read_text().splitlines()[2:]:
        c = ln.split(";")
        if len(c) > 8 and c[7] == "chuva":
            out.append((datetime.strptime(c[6][:16], "%Y-%m-%d %H:%M") - timedelta(hours=3), float(c[8])))
    return sorted(out)


def main():
    email, senha = ped.carregar_credenciais()
    token = ped.obter_token(email, senha)
    for vid, (dia, est) in VIDEOS.items():
        # dia local 00h-24h = UTC dia 03h até dia+1 03h: baixa os dois dias UTC
        d1 = (datetime.fromisoformat(dia) + timedelta(days=1)).date().isoformat()
        ped.ESTACOES = {c: (n, 0, 0) for c, n in est.items()}
        ped.baixar(email, senha, token, [dia, d1])
    for vid, (dia, est) in VIDEOS.items():
        print(f"\n=== {vid} {dia}")
        d1 = (datetime.fromisoformat(dia) + timedelta(days=1)).date().isoformat()
        for cod, nome in est.items():
            s = [x for x in serie(cod, dia) + serie(cod, d1) if x[0].date().isoformat() == dia]
            # mm/h = mm da leitura / intervalo desde a leitura anterior (10 min na chuva)
            chuva = [(t.strftime("%H:%M"), round(v * 60 / max((t - s[i - 1][0]).total_seconds() / 60, 10) if i else v * 6, 1))
                     for i, (t, v) in enumerate(s) if v > 0]
            print(f"  {nome}: total {sum(v for _, v in s):.1f} mm | mm/h (10 min) > 0: {chuva}")


if __name__ == "__main__":
    main()
