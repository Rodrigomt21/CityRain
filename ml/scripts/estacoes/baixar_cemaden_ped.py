"""Baixa dados históricos de pluviômetros CEMADEN via API oficial do PED.

Requer cadastro em https://ped.cemaden.gov.br (gratuito). As credenciais são
lidas de variáveis de ambiente ou de um arquivo .env (gitignored):

    CEMADEN_EMAIL=seu@email.com
    CEMADEN_SENHA=suasenha

Procura .env em ml/.env e na raiz do repo, nessa ordem. NUNCA commitar a senha.

Fluxo (mapeado por engenharia reversa do bundle ped_app.js e do Swagger
https://sws.cemaden.gov.br/PED/api/ui/ — ver docs/fontes-estacoes.md):
  1. POST https://ped.cemaden.gov.br/SGAA/rest/controle-token/tokens -> JWT
     (NÃO é sws.cemaden.gov.br — esse host devolve 404 para esta rota. O bundle usa
     axios com baseURL:"", ou seja, a chamada é relativa à própria origem do front,
     ped.cemaden.gov.br. Corpo: {"email": ..., "password": ...} — confirmado por
     sondagem com corpo vazio/campos inválidos, que devolve mensagens de validação
     do backend nomeando os campos exatos, ex.: "Unrecognized field \"usuario\""
     e depois "...obrigatórios e não podem ser nulos: password!".)
  2. GET  https://sws.cemaden.gov.br/PED/rest/pcds/dados_pcd
          (header token; codigo=codestacao, inicio/fim no formato aaaaMMddHHmm,
          rede=11, sensor=10 [id numérico de "Chuva", confirmado no exemplo do
          Swagger de /pcds-tipo-estacao/sensores — nunca "chuva" como string])

Uso:
    python ml/scripts/estacoes/baixar_cemaden_ped.py --teste       # valida login
    python ml/scripts/estacoes/baixar_cemaden_ped.py               # baixa tudo
    python ml/scripts/estacoes/baixar_cemaden_ped.py --dias 2026-09-01
    python ml/scripts/estacoes/baixar_cemaden_ped.py --forcar   # reconsulta os "sem dados"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RAW_DIR = REPO / "ml/data/raw/estacoes/respostas_brutas/cemaden_ped"
OUT_CSV = REPO / "ml/data/raw/estacoes/normalizado/cemaden_ped.csv"

SGAA_TOKEN_URL = "https://ped.cemaden.gov.br/SGAA/rest/controle-token/tokens"
PED_BASE = "https://sws.cemaden.gov.br/PED/rest"

# Dias-alvo das sessões de coleta (ver docs/specs/spec-historico-estacoes.md)
DIAS_ALVO = ["2026-08-04", "2026-09-01", "2026-09-13", "2026-09-23"]

# Estações CEMADEN <= 5 km dos bboxes das sessões (coordenadas do feed oficial
# resources.cemaden.gov.br/dados/311_24.json — ver docs/fontes-estacoes.md).
ESTACOES: dict[str, tuple[str, float, float]] = {
    "355030826A": ("Mooca", -23.547, -46.596),
    "355030831A": ("AC Almeida Lima", -23.55196, -46.60861),
    "355030833A": ("AC Central de SP", -23.54331, -46.63599),
    "355030857A": ("Centro", -23.541, -46.629),
    "355030812A": ("Luz", -23.53102, -46.63253),
    "355030871A": ("Ipiranga", -23.587, -46.602),
    "355030877A": ("Vila Formosa", -23.561, -46.564),
    "355030869A": ("Vila Prudente", -23.584, -46.561),
    "355030808A": ("Vila Clementino", -23.599, -46.65),
    "355030860A": ("Limão", -23.511, -46.667),
    "355030853A": ("Pinheiros", -23.563, -46.703),
    "355030878A": ("Lapa", -23.522, -46.695),
    "355030811A": ("AC Santana", -23.50248, -46.62884),
    "355030854A": ("Vila Maria", -23.502, -46.591),
    "354880701A": ("Centro (S.Caetano)", -23.609, -46.573),
}

# Pluviômetros a <= 5 km das câmeras fixas de ml/configs/coleta_fixa.yaml (feed
# resources.cemaden.gov.br/dados/311_24.json, consultado em 04/10/2026).
ESTACOES_COLETA_FIXA: dict[str, tuple[str, float, float]] = {
    # santos_gonzaga (coleta fixa, <= 5 km)
    "354850005A": ("Vila Mathias (Santos)", -23.94200, -46.33100),
    "354850010A": ("Estuario (Santos)", -23.96700, -46.30500),
    "354850012A": ("Nova Cintra (Santos)", -23.94700, -46.35600),
    "354850013A": ("Morro de São Bento (Santos)", -23.93500, -46.34100),
    "354850008A": ("Ponta da Praia (Santos)", -23.98100, -46.30000),
    "354850011A": ("Saboó (Santos)", -23.93040, -46.34490),
    "354850006A": ("Chico de Paula (Santos)", -23.93100, -46.36000),
    # praiagrande_boqueirao (coleta fixa, <= 5 km)
    "354100002A": ("Portinho (Praia Grande)", -23.98791, -46.40595),
    "355100904A": ("Parque Prainha (São Vicente)", -23.97899, -46.38380),
    # guaruja_enseada (coleta fixa, <= 5 km)
    "351870111A": ("Enseada (Guarujá)", -23.97700, -46.22200),
    "351870120A": ("Jardim São Miguel (Guarujá)", -23.98200, -46.24700),
    "351870114A": ("Balneário Pernambuco (Guarujá)", -23.97000, -46.19100),
    "351870113A": ("Santo Antonio (Guarujá)", -23.99000, -46.26500),
    "351870119A": ("Cachoeira (Guarujá)", -23.98300, -46.26600),
    "351870107A": ("Morrinhos (Guarujá)", -23.96800, -46.26000),
    # ubatuba_tenorio (coleta fixa, <= 5 km)
    "355540601A": ("Tenório (Ubatuba)", -23.46500, -45.06000),
    "355540606A": ("Estufa II (Ubatuba)", -23.45200, -45.07900),
    "355540622A": ("Centro 2 (Ubatuba)", -23.44000, -45.08200),
    "355540616A": ("Centro (Ubatuba)", -23.43400, -45.07700),
    "355540613A": ("Perequê-Açu (Ubatuba)", -23.42604, -45.06628),
    # bc_atlantica (coleta fixa, <= 5 km)
    "420200801A": ("Nações (Balneário Camboriú)", -26.98600, -48.64300),
    "420320402A": ("Monte Alegre (Camboriú)", -27.00200, -48.66500),
    "420200802A": ("Barra (Balneário Camboriú)", -27.00700, -48.59600),
    "420820303A": ("Praia Brava (Itajaí)", -26.95600, -48.64400),
    "420320405A": ("Rio Pequeno (Camboriú)", -27.03100, -48.64100),
}
ESTACOES.update(ESTACOES_COLETA_FIXA)


def carregar_credenciais() -> tuple[str, str]:
    """Lê CEMADEN_EMAIL/CEMADEN_SENHA do ambiente ou de um .env.

    Returns:
        Tupla (email, senha).

    Raises:
        SystemExit: se as credenciais não forem encontradas.
    """
    for envfile in (REPO / "ml/.env", REPO / ".env"):
        if envfile.is_file():
            for line in envfile.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    email = os.environ.get("CEMADEN_EMAIL", "")
    senha = os.environ.get("CEMADEN_SENHA", "")
    if not email or not senha:
        sys.exit(
            "Credenciais ausentes. Crie ml/.env (gitignored) com:\n"
            "  CEMADEN_EMAIL=seu@email.com\n  CEMADEN_SENHA=suasenha"
        )
    return email, senha


def _post_json(url: str, payload: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _get(url: str, params: dict, token: str) -> tuple[int, str]:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"token": token, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def obter_token(email: str, senha: str) -> str:
    """Autentica no SGAA e devolve o JWT.

    O corpo do login foi confirmado por sondagem sem credenciais reais (ver
    docs/fontes-estacoes.md e o cabeçalho deste arquivo): o backend valida o
    JSON contra a classe ``br.gov.cemaden.sgaa.model.Credential``, que só aceita
    os campos ``email`` e ``password`` (qualquer outro nome, ex. "usuario" ou
    "login", é rejeitado como "Unrecognized field"). Por isso fazemos uma única
    tentativa com o formato correto — não ficamos testando variantes contra a
    conta real do usuário.
    """
    corpo = {"email": email, "password": senha}
    status, body = _post_json(SGAA_TOKEN_URL, corpo)
    if status == 200 and body.strip():
        # resposta pode ser o token cru ou um JSON {"token": ...}
        try:
            data = json.loads(body)
            token = (
                data.get("token") or data.get("jwt") or data.get("access_token")
                or ""
            ) if isinstance(data, dict) else ""
        except json.JSONDecodeError:
            token = body.strip().strip('"')
        if token:
            return token
    sys.exit(f"Falha ao obter token. HTTP {status}: {body[:300]}")


def baixar(email: str, senha: str, token: str, dias: list[str],
           forcar: bool = False) -> list[Path]:
    """Baixa dados_pcd (sensor chuva) por estação x dia; salva respostas brutas.

    O token do PED tem um número máximo total de acessos (observado
    empiricamente: falha com "Este token excedeu o número máximo total de
    acessos permitido!" após ~11 chamadas). Por isso o token é renovado
    proativamente a cada ``RENOVAR_A_CADA`` chamadas, e também de forma
    reativa se essa mensagem específica aparecer (nesse caso a chamada é
    refeita uma única vez com o token novo).

    A cota é do CADASTRO, não do token: renovar o JWT não a reseta (observado em
    16/09 e 18/09/2026). Por isso pares que a API já respondeu com 202 "Nenhum
    resultado" são pulados — é negativa definitiva e gastaria cota à toa. Use
    ``forcar=True`` para reconsultá-los (ex.: se a estação voltar a reportar).

    Args:
        email: e-mail do cadastro no PED, para renovar o token.
        senha: senha do cadastro no PED.
        token: JWT já obtido, usado na primeira chamada.
        dias: dias no formato YYYY-MM-DD.
        forcar: reconsulta pares com 202 "Nenhum resultado" já registrado.

    Returns:
        Caminhos das respostas brutas disponíveis (baixadas agora ou já em disco).
    """
    RENOVAR_A_CADA = 5
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    salvos: list[Path] = []
    chamadas = 0
    for dia in dias:
        dia_compacto = dia.replace("-", "")
        for cod, (nome, _lat, _lon) in ESTACOES.items():
            destino = RAW_DIR / f"dados_pcd_{cod}_{dia}.json"
            if destino.exists() and destino.stat().st_size > 0:
                print(f"  [pulado, já existe] {destino.name}")
                salvos.append(destino)
                continue
            # HTTP 202 "Nenhum resultado" é negativa DEFINITIVA da API (a estação
            # não tem série nesse dia), não falha transitória. Sem esse cache, as
            # estações sem dados consomem toda a cota de acessos do token antes de
            # chegar nos pares que realmente faltam (que falharam com 401).
            erro_anterior = RAW_DIR / f"ERRO_{cod}_{dia}.txt"
            if erro_anterior.exists() and not forcar:
                texto_erro = erro_anterior.read_text()
                if "Nenhum resultado" in texto_erro:
                    print(f"  [pulado, sem dados na API] {cod} {nome} {dia}")
                    continue
            if chamadas > 0 and chamadas % RENOVAR_A_CADA == 0:
                print("  [renovando token proativamente...]")
                token = obter_token(email, senha)
                time.sleep(1)
            params = {
                "codigo": cod,
                # formato exigido pela API: aaaaMMddHHmm ou aaaaMM (confirmado
                # via mensagem de erro do backend — "aaaaMMdd" puro é rejeitado)
                "inicio": f"{dia_compacto}0000",
                "fim": f"{dia_compacto}2359",
                "rede": 11,       # rede CEMADEN observada no catálogo 311_24.json
                # 10 = "Chuva" (sensor da estação pluviométrica) — confirmado no
                # exemplo do próprio Swagger de /pcds-tipo-estacao/sensores, não
                # por tentativa e erro (evita gastar cota de acessos do token).
                "sensor": 10,
            }
            status, body = _get(f"{PED_BASE}/pcds/dados_pcd", params, token)
            chamadas += 1
            if status == 401 and "acessos" in body:
                print("  [token esgotado, renovando e tentando 1x de novo...]")
                token = obter_token(email, senha)
                time.sleep(1)
                status, body = _get(f"{PED_BASE}/pcds/dados_pcd", params, token)
                chamadas += 1
            if status != 200:
                # guarda o erro também — evidência para depuração de params
                (RAW_DIR / f"ERRO_{cod}_{dia}.txt").write_text(
                    f"params={params}\nHTTP {status}\n{body[:2000]}"
                )
                print(f"  [HTTP {status}] {cod} {nome} {dia} — erro salvo")
                time.sleep(1)
                continue
            destino.write_text(body)
            salvos.append(destino)
            print(f"  [ok] {cod} {nome} {dia} ({len(body)} bytes)")
            time.sleep(1)  # educação com a API
    return salvos


def normalizar(arquivos: list[Path]) -> int:
    """Converte as respostas brutas para o CSV no schema padrão do projeto.

    Schema: fonte,estacao_id,estacao_nome,lat,lon,ts_utc,acumulado_mm,janela_min
    A resposta do dados_pcd pode vir como JSON (lista de leituras) ou CSV;
    tratamos os dois. Campos de data/valor são detectados por nome.
    """
    linhas: list[dict] = []
    for arq in arquivos:
        cod = arq.stem.split("_")[2]
        nome, lat, lon = ESTACOES.get(cod, (cod, "", ""))
        texto = arq.read_text().strip()
        registros: list[dict] = []
        if texto.startswith("[") or texto.startswith("{"):
            data = json.loads(texto)
            if isinstance(data, dict):
                data = data.get("dados") or data.get("data") or data.get("results") or []
            registros = [r for r in data if isinstance(r, dict)]
        else:  # CSV com ';' ou ',', possivelmente precedido de linhas de aviso
            # a resposta do dados_pcd comeca com "OBS.: PCD com horario UTC!"
            linhas_txt = texto.splitlines()
            inicio = next((i for i, l in enumerate(linhas_txt) if "cod.estacao" in l
                           or l.count(";") >= 3 or l.count(",") >= 3), 0)
            linhas_txt = linhas_txt[inicio:]
            delim = ";" if linhas_txt[0].count(";") else ","
            registros = list(csv.DictReader(linhas_txt, delimiter=delim))
        for r in registros:
            ts = next((r[k] for k in r if k and k.lower().strip() == "datahora"), None)
            if ts is None:
                ts = next((r[k] for k in r if k and ("data" in k.lower()
                           or "hora" in k.lower())), None)
            valor = next((r[k] for k in r if k and k.lower().strip() == "valor"), None)
            if valor is None:
                valor = next((r[k] for k in r if k and ("valor" in k.lower()
                              or "medicao" in k.lower())), None)
            if ts is None or valor is None:
                continue
            linhas.append({
                "fonte": "cemaden_ped",
                "estacao_id": cod,
                "estacao_nome": nome,
                "lat": lat,
                "lon": lon,
                # timestamps do CEMADEN são UTC (confirmado empiricamente na via B
                # — ver docs/fontes-estacoes.md); normalizamos o sufixo Z
                "ts_utc": str(ts).replace(" ", "T").split(".")[0].rstrip("Z") + "Z",
                "acumulado_mm": valor,
                "janela_min": 10,
            })
    if linhas:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUT_CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(sorted(linhas, key=lambda x: (x["estacao_id"], x["ts_utc"])))
    return len(linhas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--teste", action="store_true",
                    help="só valida o login e uma chamada de catálogo")
    ap.add_argument("--dias", nargs="*", default=DIAS_ALVO,
                    help=f"dias YYYY-MM-DD (default: {' '.join(DIAS_ALVO)})")
    ap.add_argument("--forcar", action="store_true",
                    help="reconsulta pares que já retornaram 202 'Nenhum resultado' "
                         "(por padrão são pulados para não gastar cota do cadastro)")
    args = ap.parse_args()

    email, senha = carregar_credenciais()
    print(f"Autenticando como {email}...")
    token = obter_token(email, senha)
    print(f"Token obtido ({len(token)} chars).")

    if args.teste:
        status, body = _get(f"{PED_BASE}/pcds-cadastro/dados-cadastrais",
                            {"codestacao": "355030871A", "formato": "json"}, token)
        print(f"Teste dados-cadastrais (Ipiranga): HTTP {status}")
        print(body[:500])
        return

    print(f"Baixando {len(ESTACOES)} estações x {len(args.dias)} dias...")
    baixar(email, senha, token, list(args.dias), forcar=args.forcar)
    # Normaliza TODOS os brutos já salvos, não só os desta execução: o CSV é
    # reescrito do zero, então baixar um dia novo apagava os dias anteriores.
    n = normalizar(sorted(RAW_DIR.glob("dados_pcd_*")))
    print(f"\n{n} leituras normalizadas -> {OUT_CSV}")
    if n == 0:
        print("Nenhuma leitura extraída — inspecione os brutos em "
              f"{RAW_DIR} (inclusive arquivos ERRO_*.txt) para ajustar params.")


if __name__ == "__main__":
    main()
