# Câmera fixa — Plano B: Coleta, rótulo e dataset

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ter o fluxo completo de dados da câmera fixa: frames ao vivo indo para o backend, colheita de `seco` e de chuva do DVR, revisão por amostra e um CSV de splits por evento e por câmera pronto para o treino.

**Architecture:** Tudo reaproveita o contrato de frame da Jetson (`frame_*.jpg` + `.json`) e a rotulagem por pluviômetro que já existe (`gerar_manifest.py`). O que é novo: envio ao `/ingest` no `coletor.py`, um modo de colheita seca no `recuperar_dvr.py`, painéis de revisão e um montador de splits próprio do modelo fixo (`montar_splits_fixa.py`). Os comandos que dependem de rede, de CEMADEN ou de olho humano ficam numa tarefa de execução separada (Task 5).

**Tech Stack:** Python 3.11+ (`ml/.venv`), PyYAML, requests, Pillow, NumPy, pytest. Sem torch neste plano.

**Spec:** `docs/specs/spec-camera-fixa.md` (seções CF1 a CF4). Mapa do código: `docs/CODEBASE_MAP.md`.

## Global Constraints

- Rótulo **sempre** de pluviômetro; nenhum script deste plano altera classe à mão. A revisão humana só **exclui** frames (câmera tampada, congelada, tela de offline).
- Limiares: `seco` = 0 com confirmação regional de ±60 min; `garoa` ≤ 2,5; `moderada` ≤ 10; `forte` > 10 mm/h; zona morta de ±15%.
- Unidade estatística é o **evento** (`evento_id = <câmera>__<data>`); splits nunca separam frames do mesmo evento.
- Só transmissões públicas de propósito. Nunca câmeras IP expostas sem autorização.
- Testes rodam sem torch: `ml/.venv/bin/python -m pytest -q ml/tests`. Scripts são carregados nos testes por `importlib.util.spec_from_file_location` (padrão de `ml/tests/test_coleta_fixa.py`).
- Credenciais (tokens dos dispositivos, CEMADEN) nunca vão para o Git: `ml/configs/coleta_fixa_tokens.json` e `.env` são gitignored.
- Comentários e docstrings em português; nomes em português no ML (padrão do código atual).
- Commits `tipo: descrição` em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Sem push.

## Review Focus

1. **Backend fora do ar durante o envio ao vivo** → o frame continua gravado em disco, o coletor registra a falha e segue para a próxima câmera (Task 1).
2. **Câmera sem token configurado com `--enviar`** → aviso único no início e a câmera só grava em disco; nunca derruba o coletor (Task 1).
3. **Estações sem leitura num trecho (buraco no CEMADEN)** → esse trecho não conta como seco; nada de inventar `seco` sem dado (Task 2).
4. **Câmera com posição ainda não verificada** → fica fora do treino e do teste, e o resumo diz quantos frames saíram por isso (Task 4).
5. **Câmera sem nenhum frame `seco` para servir de referência** → linhas ficam com `referencia` vazia e o resumo aponta a câmera; o treino com referência as descarta de forma explícita (Task 4; Plano C Task 3).

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `ml/scripts/coleta_fixa/coletor.py` | modificar | `posicao_verificada`, `fonte_publica`, envio ao `/ingest` |
| `ml/configs/coleta_fixa.yaml` | modificar | `backend_url`, campos novos por fonte |
| `.gitignore` | modificar | `ml/configs/coleta_fixa_tokens.json` |
| `ml/scripts/coleta_fixa/recuperar_dvr.py` | modificar | `janelas_secas` e `--modo-seco` |
| `ml/configs/rotulagem_coleta_fixa_5km.yaml` | criar | rotulagem paralela a 5 km (CF3.2) |
| `ml/scripts/dataset/paineis_revisao_fixa.py` | criar | painéis por (câmera, classe) e modelo de `revisao.csv` |
| `ml/scripts/dataset/montar_splits_fixa.py` | criar | CSV de splits do modelo fixo |
| `ml/configs/splits_fixa_v1.yaml` | criar | config do montador |
| `ml/tests/test_coleta_fixa.py` | modificar | testes do envio |
| `ml/tests/test_dvr_seco.py` | criar | testes das janelas secas |
| `ml/tests/test_paineis_revisao.py` | criar | testes da amostragem e das exclusões |
| `ml/tests/test_splits_fixa.py` | criar | testes do montador |

---

### Task 1: Envio ao vivo no `coletor.py`

**Files:**
- Modify: `ml/scripts/coleta_fixa/coletor.py`
- Modify: `ml/configs/coleta_fixa.yaml`, `.gitignore`
- Test: `ml/tests/test_coleta_fixa.py`

**Interfaces:**
- Produces:
  - `Fonte` ganha `posicao_verificada: bool = False` e `fonte_publica: str = ""` (lidos do YAML por `carregar_fontes`).
  - `nome_device(fonte_id: str) -> str` → `f"fixa-{fonte_id}"` (convenção usada pelo backend e pelas referências do Plano C).
  - `token_da_fonte(fonte_id: str, arquivo_tokens: Path | None) -> str | None`: variável `CITYRAIN_TOKEN_<FONTE_ID_EM_MAIUSCULAS>` tem precedência; depois o JSON `{ "<fonte_id>": "<token>" }`.
  - `metadados_ingest(meta_frame: dict, demo: dict | None = None) -> dict`: monta o JSON do campo `metadata` do `/ingest` (`captured_at`, `latitude`, `longitude`, `source_type="camera_fixa"`, `metadata.fonte`, e `metadata.demo` quando houver).
  - `enviar_frame(jpg: Path, backend_url: str, token: str, sessao=None, demo: dict | None = None, timeout: float = 30) -> int`: POST multipart; devolve o status HTTP, ou `0` em erro de rede.
  - CLI: `--enviar` (envia cada frame novo), `--intervalo-s N` (sobrescreve o intervalo de todas as fontes), `--tokens PATH` (default `ml/configs/coleta_fixa_tokens.json`).
- O Plano D (`replay_evento.py`) importa `metadados_ingest`, `enviar_frame` e `token_da_fonte`.

- [ ] **Step 1: Testes que falham** (acrescentar a `ml/tests/test_coleta_fixa.py`)

```python
class _Resp:
    def __init__(self, status):
        self.status_code = status


class _SessaoFalsa:
    def __init__(self, status=201, erro=None):
        self.status, self.erro, self.chamadas = status, erro, []

    def post(self, url, files=None, data=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "files": files, "data": data, "headers": headers})
        if self.erro:
            raise self.erro
        return _Resp(self.status)


def test_nome_device_segue_convencao():
    assert col.nome_device("sp_centro_geolan") == "fixa-sp_centro_geolan"


def test_token_da_variavel_tem_precedencia(tmp_path, monkeypatch):
    arq = tmp_path / "tokens.json"
    arq.write_text(json.dumps({"cam1": "do-arquivo"}))
    assert col.token_da_fonte("cam1", arq) == "do-arquivo"
    monkeypatch.setenv("CITYRAIN_TOKEN_CAM1", "da-env")
    assert col.token_da_fonte("cam1", arq) == "da-env"
    assert col.token_da_fonte("outra", arq) is None
    assert col.token_da_fonte("cam1", tmp_path / "nao_existe.json") == "da-env"


def test_metadados_do_ingest(tmp_path):
    quando = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)
    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, quando)
    meta = col.metadados_ingest(json.loads(jpg.with_suffix(".json").read_text()))
    assert meta["captured_at"] == quando.isoformat()
    assert (meta["latitude"], meta["longitude"]) == (-23.5, -46.6)
    assert meta["source_type"] == "camera_fixa"
    assert meta["metadata"]["fonte"] == "cam1"
    assert "demo" not in meta["metadata"]
    com_demo = col.metadados_ingest(json.loads(jpg.with_suffix(".json").read_text()), demo={"origem": "x"})
    assert com_demo["metadata"]["demo"] == {"origem": "x"}


def test_enviar_frame_faz_post_multipart(tmp_path):
    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, datetime.now(timezone.utc))
    s = _SessaoFalsa(201)
    assert col.enviar_frame(jpg, "http://api/api/v1/ingest", "tok", sessao=s) == 201
    ch = s.chamadas[0]
    assert ch["headers"] == {"Authorization": "Bearer tok"}
    assert ch["files"]["image"][2] == "image/jpeg"
    assert json.loads(ch["data"]["metadata"])["source_type"] == "camera_fixa"


def test_enviar_frame_com_rede_fora_devolve_zero(tmp_path):
    import requests

    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, datetime.now(timezone.utc))
    s = _SessaoFalsa(erro=requests.ConnectionError("sem rede"))
    assert col.enviar_frame(jpg, "http://api", "tok", sessao=s) == 0
    assert jpg.exists()


def test_carrega_campos_novos_da_fonte():
    f = _fonte(posicao_verificada=True, fonte_publica="https://exemplo.gov.br/cameras")
    assert f.posicao_verificada is True and f.fonte_publica.startswith("https://")
    assert _fonte().posicao_verificada is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_coleta_fixa.py`
Expected: FAIL com `AttributeError: module 'coletor' has no attribute 'nome_device'`.

- [ ] **Step 3: Implementar**

Em `Fonte`, depois de `descricao`:

```python
    posicao_verificada: bool = False  # lat/lon conferida no mapa pela imagem (CF1.1)
    fonte_publica: str = ""           # página oficial que publica a câmera (CF1)
```

Em `carregar_fontes`, passar `posicao_verificada=bool(f.get("posicao_verificada", False))` e `fonte_publica=f.get("fonte_publica", "")`.

Novas funções (depois de `gravar_frame`):

```python
# ------------------------------------------------------------------ envio ao backend
def nome_device(fonte_id: str) -> str:
    """Nome do dispositivo da câmera no backend (e da pasta de referências do modelo fixo)."""
    return f"fixa-{fonte_id}"


def token_da_fonte(fonte_id: str, arquivo_tokens: Path | None) -> str | None:
    """Token do dispositivo: CITYRAIN_TOKEN_<ID> no ambiente, senão o JSON de tokens (gitignored)."""
    env = os.environ.get(f"CITYRAIN_TOKEN_{fonte_id.upper()}")
    if env:
        return env
    if arquivo_tokens and Path(arquivo_tokens).is_file():
        return json.loads(Path(arquivo_tokens).read_text()).get(fonte_id)
    return None


def metadados_ingest(meta_frame: dict, demo: dict | None = None) -> dict:
    """JSON do campo `metadata` do POST /api/v1/ingest a partir do .json do frame.

    O backend ignora lat/lon de câmera fixa (usa o cadastro), mas elas vão junto para
    o registro ficar completo se o dispositivo for cadastrado errado como móvel.
    """
    extra: dict = {"fonte": meta_frame["device_id"]}
    if demo:
        extra["demo"] = demo
    return {
        "captured_at": meta_frame["capturado_em_utc"],
        "latitude": meta_frame["gps"]["latitude"],
        "longitude": meta_frame["gps"]["longitude"],
        "source_type": "camera_fixa",
        "metadata": extra,
    }


def enviar_frame(jpg: Path, backend_url: str, token: str, sessao=None, demo: dict | None = None,
                 timeout: float = 30) -> int:
    """POST do par ao /ingest. Devolve o status HTTP, ou 0 se a rede falhou. Nunca apaga o frame."""
    import requests

    sessao = sessao or requests
    meta = json.loads(jpg.with_suffix(".json").read_text())
    try:
        r = sessao.post(
            backend_url,
            files={"image": (jpg.name, jpg.read_bytes(), "image/jpeg")},
            data={"metadata": json.dumps(metadados_ingest(meta, demo))},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        return r.status_code
    except requests.RequestException:
        return 0
```

`rodada` ganha os parâmetros `envio: dict | None = None` (chaves `url`, `tokens: dict[str, str]`). Depois de gravar um frame novo:

```python
            if envio and caminho and f.id in envio["tokens"]:
                status = enviar_frame(caminho, envio["url"], envio["tokens"][f.id])
                estado += f" -> ingest {status or 'sem rede'}"
```

Em `main`:

```python
    ap.add_argument("--enviar", action="store_true", help="envia cada frame novo ao POST /api/v1/ingest")
    ap.add_argument("--intervalo-s", type=float, help="sobrescreve o intervalo de todas as fontes")
    ap.add_argument("--tokens", type=Path, default=RAIZ / "ml/configs/coleta_fixa_tokens.json")
    ...
    if args.intervalo_s:
        for f in fontes:
            f.intervalo_s = args.intervalo_s
    envio = None
    if args.enviar:
        tokens = {f.id: t for f in fontes if (t := token_da_fonte(f.id, args.tokens))}
        for f in fontes:
            if f.id not in tokens:
                print(f"[coletor] {f.id}: sem token, só grava em disco", flush=True)
        envio = {"url": cfg["backend_url"], "tokens": tokens}
```

e passar `envio` para `rodada` nos dois pontos onde ela é chamada.

Em `ml/configs/coleta_fixa.yaml`, no topo:

```yaml
# Envio ao vivo (coletor.py --enviar): um dispositivo por câmera, nome fixa-<id>,
# token em CITYRAIN_TOKEN_<ID> ou em ml/configs/coleta_fixa_tokens.json (gitignored).
backend_url: https://api-production-046f.up.railway.app/api/v1/ingest
```

Em cada fonte ativa, acrescentar `posicao_verificada: false` e `fonte_publica: ""` (a Task 5 preenche). Em `.gitignore`: `ml/configs/coleta_fixa_tokens.json`.

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_coleta_fixa.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml .gitignore ml/tests/test_coleta_fixa.py
git commit -m "feat(coleta): coletor envia frames de câmera fixa ao /ingest"
```

---

### Task 2: Colheita de `seco` no DVR (`--modo-seco`)

Hoje o `--onde-choveu` só baixa chuva e margem. O modelo fixo precisa de `seco` de dia e de noite em **todas** as câmeras (meta: ≥ 300 por câmera).

**Files:**
- Modify: `ml/scripts/coleta_fixa/recuperar_dvr.py`
- Test: `ml/tests/test_dvr_seco.py`

**Interfaces:**
- Produces: `janelas_secas(fonte, leituras: list[dict], raio_km: float, inicio: datetime, fim: datetime, duracao: timedelta = timedelta(minutes=30), folga: timedelta = timedelta(minutes=60), min_estacoes: int = 2, max_janelas: int = 6) -> list[tuple[datetime, datetime]]`.
  - Divide `[inicio, fim)` em blocos de 10 min. Bloco **seco** = ≥ `min_estacoes` estações a ≤ `raio_km` com leitura nele e todas com `acumulado_mm == 0`. Bloco com qualquer chuva = **chuva**. O resto = **sem dado** (não conta como seco).
  - Uma janela é um trecho de `duracao` cujo intervalo `[a − folga, b + folga]` é todo de blocos secos.
  - Escolhe até `max_janelas`, alternando dia e noite (`periodo` pela mesma regra da rotulagem: dia = [06:00, 18:30) em UTC−3), sem sobreposição, em ordem de tempo.
- CLI: `--modo-seco` (usa `janelas_secas`), `--max-janelas` (default 6), `--duracao-min` (default 30). Recomendo `--passo-s 300` neste modo.

- [ ] **Step 1: Testes que falham** (`ml/tests/test_dvr_seco.py`)

```python
"""Janelas secas confirmadas por várias estações, para colher `seco` no DVR."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_P = Path(__file__).resolve().parents[1] / "scripts" / "coleta_fixa" / "recuperar_dvr.py"
sys.path.insert(0, str(_P.parent))
_spec = importlib.util.spec_from_file_location("recuperar_dvr", _P)
dvr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dvr
_spec.loader.exec_module(dvr)

CAM = SimpleNamespace(id="cam", lat=-23.55, lon=-46.63)
T0 = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)  # 00:00 local


def leituras(horas: int, chuva_em: set[int] = frozenset(), buraco_em: set[int] = frozenset(), estacoes=2):
    """Uma leitura de 10 min por estação; `chuva_em`/`buraco_em` são índices de bloco."""
    out = []
    for e in range(estacoes):
        for i in range(horas * 6):
            if i in buraco_em:
                continue
            ts = T0 + timedelta(minutes=10 * (i + 1))
            out.append({"estacao_id": f"E{e}", "lat": -23.55 + 0.005 * e, "lon": -46.63,
                        "ts_utc": ts.isoformat(), "acumulado_mm": "0.4" if i in chuva_em else "0", "janela_min": "10"})
    return out


def test_dia_todo_seco_rende_janelas_de_dia_e_de_noite():
    js = dvr.janelas_secas(CAM, leituras(24), 5.0, T0, T0 + timedelta(hours=24), max_janelas=4)
    assert len(js) == 4
    periodos = {dvr.periodo_local(a) for a, _ in js}
    assert periodos == {"dia", "noite"}
    assert all(b - a == timedelta(minutes=30) for a, b in js)
    assert all(js[i][1] <= js[i + 1][0] for i in range(len(js) - 1))


def test_chuva_afasta_a_janela_pela_folga():
    chuva = set(range(18, 24))  # 03:00–04:00 UTC+0 depois de T0
    js = dvr.janelas_secas(CAM, leituras(8, chuva_em=chuva), 5.0, T0, T0 + timedelta(hours=8), max_janelas=10)
    inicio_chuva, fim_chuva = T0 + timedelta(hours=3), T0 + timedelta(hours=4)
    for a, b in js:
        assert b + timedelta(minutes=60) <= inicio_chuva or a - timedelta(minutes=60) >= fim_chuva


def test_buraco_de_dado_nao_vira_seco():
    js = dvr.janelas_secas(CAM, leituras(3, buraco_em=set(range(0, 18))), 5.0, T0, T0 + timedelta(hours=3))
    assert js == []


def test_uma_estacao_so_nao_basta():
    assert dvr.janelas_secas(CAM, leituras(24, estacoes=1), 5.0, T0, T0 + timedelta(hours=24)) == []


def test_estacao_longe_nao_conta():
    longe = [dict(r, lat=-24.5) for r in leituras(24)]
    assert dvr.janelas_secas(CAM, longe, 5.0, T0, T0 + timedelta(hours=24)) == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_dvr_seco.py`
Expected: FAIL com `AttributeError: ... 'janelas_secas'`.

- [ ] **Step 3: Implementar** (em `recuperar_dvr.py`, depois de `janelas_com_chuva`)

```python
FUSO_LOCAL = timezone(timedelta(hours=-3))
BLOCO = timedelta(minutes=10)


def periodo_local(quando: datetime) -> str:
    """Mesma regra de gerar_manifest.py: dia = [06:00, 18:30) no horário local."""
    h = quando.astimezone(FUSO_LOCAL)
    minutos = h.hour * 60 + h.minute
    return "dia" if 6 * 60 <= minutos < 18 * 60 + 30 else "noite"


def _bloco(ts: datetime) -> datetime:
    return ts - timedelta(minutes=ts.minute % 10, seconds=ts.second, microseconds=ts.microsecond)


def janelas_secas(fonte, leituras: list[dict], raio_km: float, inicio: datetime, fim: datetime,
                  duracao: timedelta = timedelta(minutes=30), folga: timedelta = timedelta(minutes=60),
                  min_estacoes: int = 2, max_janelas: int = 6) -> list[tuple[datetime, datetime]]:
    """Trechos comprovadamente secos (várias estações perto, todas zeradas, com folga dos dois lados).

    Bloco sem leitura não é seco: buraco no CEMADEN não pode virar rótulo.
    """
    por_bloco: dict[datetime, dict[str, float]] = {}
    for r in leituras:
        if _hav_km(fonte.lat, fonte.lon, float(r["lat"]), float(r["lon"])) > raio_km:
            continue
        fim_leitura = datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00"))
        b = _bloco(fim_leitura - timedelta(minutes=int(r.get("janela_min") or 10)))
        por_bloco.setdefault(b, {})[r.get("estacao_id", f"{r['lat']},{r['lon']}")] = float(r["acumulado_mm"])

    def seco(b: datetime) -> bool:
        v = por_bloco.get(b, {})
        return len(v) >= min_estacoes and all(x == 0 for x in v.values())

    candidatas = []
    a = _bloco(inicio) + (BLOCO if inicio != _bloco(inicio) else timedelta(0))
    while a + duracao <= fim:
        b = a + duracao
        t, ok = a - folga, True
        while t < b + folga:
            if not seco(_bloco(t)):
                ok = False
                break
            t += BLOCO
        if ok:
            candidatas.append((a, b))
        a += BLOCO

    escolhidas: list[tuple[datetime, datetime]] = []
    filas = {p: [c for c in candidatas if periodo_local(c[0]) == p] for p in ("noite", "dia")}
    vez = 0
    while len(escolhidas) < max_janelas and any(filas.values()):
        p = ("noite", "dia")[vez % 2]
        vez += 1
        while filas[p]:
            c = filas[p].pop(0)
            if all(c[1] <= e[0] or c[0] >= e[1] for e in escolhidas):
                escolhidas.append(c)
                break
    return sorted(escolhidas)
```

No `main`: `ap.add_argument("--modo-seco", action="store_true")`, `--max-janelas` (int, 6) e `--duracao-min` (float, 30). Ler as leituras também quando `--modo-seco`. No laço por fonte:

```python
        if args.modo_seco:
            janelas = janelas_secas(f, leituras, args.raio_km, inicio_dvr, dvr.head_t,
                                    duracao=timedelta(minutes=args.duracao_min), max_janelas=args.max_janelas)
        elif args.onde_choveu:
            ...
```

Acrescentar ao docstring do módulo o uso `--modo-seco --passo-s 300`.

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_dvr_seco.py ml/tests/test_coleta_fixa.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/coleta_fixa/recuperar_dvr.py ml/tests/test_dvr_seco.py
git commit -m "feat(coleta): modo seco no DVR com confirmação de várias estações"
```

---

### Task 3: Rotulagem a 5 km e painéis de revisão

**Files:**
- Create: `ml/configs/rotulagem_coleta_fixa_5km.yaml`
- Create: `ml/scripts/dataset/paineis_revisao_fixa.py`
- Test: `ml/tests/test_paineis_revisao.py`

**Interfaces:**
- Produces:
  - `amostrar_por_grupo(linhas: list[dict], n: int, seed: int) -> dict[tuple[str, str], list[dict]]` — chave `(camera, classe)`; só linhas com `classe` preenchida; amostra determinística.
  - `montar_painel(caminhos: list[Path], colunas: int = 6, lado: int = 256) -> PIL.Image.Image` — grade com o nome do arquivo em cada célula; caminho ilegível vira célula cinza com "ilegível".
  - `ler_exclusoes(csv_path: Path) -> set[tuple[str, str]]` — `(pasta, arquivo)` das linhas com `excluir` em `{"1", "sim", "s", "x"}`; arquivo ausente → conjunto vazio.
  - CLI: `paineis_revisao_fixa.py --manifest <csv> [--manifest <csv> ...] --raiz-frames ml/data/raw/coleta_fixa --saida ml/data/review/camera_fixa --n 24 --seed 0` → `painel_<camera>_<classe>.jpg` e `revisao.csv` (`pasta,arquivo,camera,classe,manifest,excluir,motivo`), preservando marcações já existentes em `revisao.csv`.
- O `rotulagem_coleta_fixa_5km.yaml` é cópia do `rotulagem_coleta_fixa.yaml` com `raio_max_km: 5.0`, `saida_manifest: ml/data/manifests/manifest_coleta_fixa_5km.csv` e `saida_relatorio: ml/data/manifests/manifest_coleta_fixa_5km_relatorio.json`. Comentário no topo: "CF3.2 — só moderada/forte daqui entram no treino, e só depois da revisão".

- [ ] **Step 1: Testes que falham** (`ml/tests/test_paineis_revisao.py`)

```python
"""Amostragem para revisão visual e leitura das exclusões marcadas."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

_P = Path(__file__).resolve().parents[1] / "scripts" / "dataset" / "paineis_revisao_fixa.py"
_spec = importlib.util.spec_from_file_location("paineis_revisao_fixa", _P)
pr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pr
_spec.loader.exec_module(pr)


def _linhas():
    out = []
    for cam in ("a", "b"):
        for i in range(50):
            out.append({"pasta": cam, "arquivo": f"f{i:03d}.jpg", "classe": "garoa" if i % 2 else "seco"})
    out.append({"pasta": "a", "arquivo": "x.jpg", "classe": ""})
    return out


def test_amostra_por_camera_e_classe_e_deterministica():
    g1 = pr.amostrar_por_grupo(_linhas(), 10, seed=0)
    g2 = pr.amostrar_por_grupo(_linhas(), 10, seed=0)
    assert set(g1) == {("a", "garoa"), ("a", "seco"), ("b", "garoa"), ("b", "seco")}
    assert all(len(v) == 10 for v in g1.values())
    assert g1 == g2


def test_grupo_pequeno_vem_inteiro():
    linhas = [{"pasta": "c", "arquivo": "u.jpg", "classe": "forte"}]
    assert len(pr.amostrar_por_grupo(linhas, 24, 0)[("c", "forte")]) == 1


def test_painel_tem_celula_para_cada_imagem(tmp_path):
    caminhos = []
    for i in range(7):
        p = tmp_path / f"{i}.jpg"
        Image.new("RGB", (64, 48), (i * 30, 0, 0)).save(p)
        caminhos.append(p)
    caminhos.append(tmp_path / "nao_existe.jpg")
    painel = pr.montar_painel(caminhos, colunas=4, lado=50)
    assert painel.size == (4 * 50, 2 * 50)


def test_le_exclusoes_marcadas(tmp_path):
    csv_path = tmp_path / "revisao.csv"
    csv_path.write_text(
        "pasta,arquivo,camera,classe,manifest,excluir,motivo\n"
        "a,f1.jpg,a,garoa,m.csv,1,congelada\n"
        "a,f2.jpg,a,garoa,m.csv,,\n"
        "b,f3.jpg,b,seco,m.csv,sim,tampada\n"
    )
    assert pr.ler_exclusoes(csv_path) == {("a", "f1.jpg"), ("b", "f3.jpg")}
    assert pr.ler_exclusoes(tmp_path / "nao_existe.csv") == set()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_paineis_revisao.py`
Expected: FAIL (arquivo do script não existe).

- [ ] **Step 3: Implementar `ml/scripts/dataset/paineis_revisao_fixa.py`**

```python
#!/usr/bin/env python3
"""Painéis de revisão visual por (câmera, classe) para o dataset da câmera fixa (CF3.1).

A revisão NÃO muda rótulo: o rótulo vem do pluviômetro. Ela só marca frames a
excluir por defeito da imagem (câmera tampada, congelada, tela de offline,
transmissão trocada). Marque `excluir=1` e um `motivo` no revisao.csv.

Uso:
    ml/.venv/bin/python ml/scripts/dataset/paineis_revisao_fixa.py \
        --manifest ml/data/manifests/manifest_coleta_fixa.csv \
        --manifest ml/data/manifests/manifest_coleta_fixa_5km.csv \
        --raiz-frames ml/data/raw/coleta_fixa --saida ml/data/review/camera_fixa
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[3]
MARCAS_EXCLUIR = {"1", "sim", "s", "x"}
COLUNAS_REVISAO = ["pasta", "arquivo", "camera", "classe", "manifest", "excluir", "motivo"]


def amostrar_por_grupo(linhas: list[dict], n: int, seed: int) -> dict[tuple[str, str], list[dict]]:
    """Até `n` linhas por (câmera, classe), sorteio determinístico."""
    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in linhas:
        if r.get("classe"):
            grupos.setdefault((r["pasta"], r["classe"]), []).append(r)
    saida = {}
    for chave in sorted(grupos):
        rs = sorted(grupos[chave], key=lambda r: r["arquivo"])
        rng = random.Random(f"{seed}|{chave[0]}|{chave[1]}")
        saida[chave] = rs if len(rs) <= n else sorted(rng.sample(rs, n), key=lambda r: r["arquivo"])
    return saida


def montar_painel(caminhos: list[Path], colunas: int = 6, lado: int = 256) -> Image.Image:
    linhas_grade = max(1, -(-len(caminhos) // colunas))
    painel = Image.new("RGB", (colunas * lado, linhas_grade * lado), (30, 30, 30))
    d = ImageDraw.Draw(painel)
    for i, p in enumerate(caminhos):
        x, y = (i % colunas) * lado, (i // colunas) * lado
        try:
            img = Image.open(p).convert("RGB")
            img.thumbnail((lado, lado - 14))
            painel.paste(img, (x, y))
            rotulo = Path(p).name
        except (OSError, ValueError):
            d.rectangle([x, y, x + lado - 1, y + lado - 1], fill=(90, 90, 90))
            rotulo = "ilegível"
        d.text((x + 3, y + lado - 13), rotulo[:40], fill=(255, 255, 0))
    return painel


def ler_exclusoes(csv_path: Path) -> set[tuple[str, str]]:
    if not Path(csv_path).is_file():
        return set()
    with open(csv_path, newline="") as f:
        return {(r["pasta"], r["arquivo"]) for r in csv.DictReader(f) if (r.get("excluir") or "").strip().lower() in MARCAS_EXCLUIR}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, action="append", required=True)
    ap.add_argument("--raiz-frames", type=Path, default=RAIZ / "ml/data/raw/coleta_fixa")
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/data/review/camera_fixa")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    args.saida.mkdir(parents=True, exist_ok=True)
    rev_path = args.saida / "revisao.csv"
    anteriores = {}
    if rev_path.is_file():
        with open(rev_path, newline="") as f:
            anteriores = {(r["pasta"], r["arquivo"]): r for r in csv.DictReader(f)}

    novas = dict(anteriores)
    for man in args.manifest:
        with open(man, newline="") as f:
            linhas = list(csv.DictReader(f))
        for (cam, classe), rs in amostrar_por_grupo(linhas, args.n, args.seed).items():
            caminhos = [args.raiz_frames / r["pasta"] / r["arquivo"] for r in rs]
            montar_painel(caminhos).save(args.saida / f"painel_{man.stem}_{cam}_{classe}.jpg", quality=85)
            for r in rs:
                chave = (r["pasta"], r["arquivo"])
                novas.setdefault(chave, {"pasta": r["pasta"], "arquivo": r["arquivo"], "camera": cam,
                                         "classe": classe, "manifest": man.name, "excluir": "", "motivo": ""})
    with open(rev_path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLUNAS_REVISAO)
        wr.writeheader()
        for chave in sorted(novas):
            wr.writerow({k: novas[chave].get(k, "") for k in COLUNAS_REVISAO})
    print(f"[revisão] {len(novas)} frames em {rev_path.relative_to(RAIZ)}; painéis em {args.saida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
```

Criar `ml/configs/rotulagem_coleta_fixa_5km.yaml` copiando `rotulagem_coleta_fixa.yaml` e mudando só os três campos descritos em Interfaces, mais o comentário do topo.

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_paineis_revisao.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/dataset/paineis_revisao_fixa.py ml/configs/rotulagem_coleta_fixa_5km.yaml ml/tests/test_paineis_revisao.py
git commit -m "feat(dataset): painéis de revisão da câmera fixa e rotulagem paralela a 5 km"
```

---

### Task 4: Montador de splits do modelo fixo

**Files:**
- Create: `ml/scripts/dataset/montar_splits_fixa.py`
- Create: `ml/configs/splits_fixa_v1.yaml`
- Test: `ml/tests/test_splits_fixa.py`

**Interfaces:**
- Consumes: `ler_exclusoes` (Task 3), `posicao_verificada` no YAML de coleta (Task 1).
- Produces: CSV com colunas **exatas**
  `caminho,classe,mm_h,particao,origem,evento_id,camera,periodo,ts_utc,referencia,metodo_rotulo`
  - `caminho` e `referencia` relativos à raiz do repo.
  - `particao` ∈ `train`, `val`, `ircnn`, `test_camera`, `test_prospectivo`, `referencia`.
  - `origem` ∈ `live`, `irCNN`. `camera = "ircnn"` nas linhas do irCNN.
- Funções:
  - `carregar_lives(manifest: Path, raiz_frames_rel: str, metodo_padrao: str = "") -> list[dict]` — só linhas com classe.
  - `acrescentar_5km(lives: list[dict], linhas_5km: list[dict], classes: set[str]) -> list[dict]` — acrescenta só frames **sem** rótulo na regra estrita e com classe em `classes` a 5 km; `metodo_rotulo = "raio_5km"`.
  - `carregar_ircnn(manifest: Path, prefixo: str) -> list[dict]`.
  - `escolher_referencias(linhas: list[dict], congelamento: datetime) -> dict[tuple[str, str], dict]` — por `(camera, periodo)`, o `seco` mediano no tempo; nas lives só antes do congelamento.
  - `atribuir_particoes(linhas: list[dict], camera_teste: str, congelamento: datetime) -> None` (in-place).
  - `limitar_por_evento_classe(linhas: list[dict], maximo: int) -> list[dict]` — só mexe em `train`.
  - `montar(cfg: dict, raiz: Path) -> tuple[list[dict], dict]` (linhas, resumo).
- O Plano C lê esse CSV pelas colunas acima.

- [ ] **Step 1: Testes que falham** (`ml/tests/test_splits_fixa.py`)

```python
"""Splits do modelo fixo: por evento e por câmera, com referência seca por período."""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

_P = Path(__file__).resolve().parents[1] / "scripts" / "dataset" / "montar_splits_fixa.py"
sys.path.insert(0, str(_P.parent))
_spec = importlib.util.spec_from_file_location("montar_splits_fixa", _P)
ms = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ms
_spec.loader.exec_module(ms)

CONG = datetime(2026, 10, 13, tzinfo=timezone.utc)
CAB_MAN = ["arquivo", "pasta", "evento_id", "ts_utc", "mm_h", "classe", "metodo_rotulo", "motivo_exclusao", "periodo"]


def _man(path: Path, linhas: list[dict]) -> Path:
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CAB_MAN)
        wr.writeheader()
        for r in linhas:
            wr.writerow({k: r.get(k, "") for k in CAB_MAN})
    return path


def L(cam, dia, hora, classe, periodo="dia", mm="0.0", motivo=""):
    ts = f"2026-10-{dia:02d}T{hora:02d}:00:00Z"
    return {"arquivo": f"frame_{dia}_{hora}.jpg", "pasta": cam, "evento_id": f"{cam}__2026-10-{dia:02d}",
            "ts_utc": ts, "mm_h": mm, "classe": classe, "metodo_rotulo": "estacao" if classe else "",
            "motivo_exclusao": motivo, "periodo": periodo}


def _cfg(tmp_path, lives, ircnn=None, l5=None, verificadas=("a", "b", "bc"), revisao=""):
    coleta = tmp_path / "coleta.yaml"
    coleta.write_text("fontes:\n" + "".join(
        f"  - {{id: {c}, tipo: youtube, url: u, lat: 0, lon: 0, posicao_verificada: {str(c in verificadas).lower()}}}\n"
        for c in ("a", "b", "bc")))
    ir = tmp_path / "ircnn.csv"
    with open(ir, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["caminho", "classe", "mm_h", "evento_id", "periodo"])
        wr.writeheader()
        for r in ircnn or []:
            wr.writerow(r)
    cfg = {
        "manifest_lives": str(_man(tmp_path / "lives.csv", lives)),
        "manifest_ircnn": str(ir), "prefixo_ircnn": "ml/",
        "raiz_frames_lives": "ml/data/raw/coleta_fixa",
        "coleta_fixa_config": str(coleta), "exigir_posicao_verificada": True,
        "camera_teste": "bc", "congelamento_utc": "2026-10-13T00:00:00Z",
        "max_por_evento_classe": 200, "classes_5km": ["moderada", "forte"],
        "revisao_csv": revisao,
    }
    if l5 is not None:
        cfg["manifest_lives_5km"] = str(_man(tmp_path / "l5.csv", l5))
    return cfg


def _por(linhas, **kw):
    return [r for r in linhas if all(r[k] == v for k, v in kw.items())]


def test_camera_de_teste_inteira_vai_para_test_camera(tmp_path):
    lives = [L("a", 1, 15, "garoa"), L("a", 2, 15, "garoa"), L("bc", 1, 15, "moderada"), L("bc", 1, 16, "seco")]
    linhas, _ = ms.montar(_cfg(tmp_path, lives), tmp_path)
    assert {r["particao"] for r in _por(linhas, camera="bc") if r["particao"] != "referencia"} == {"test_camera"}


def test_depois_do_congelamento_e_prospectivo(tmp_path):
    lives = [L("a", 1, 15, "garoa"), L("a", 14, 15, "garoa"), L("a", 2, 15, "seco")]
    linhas, _ = ms.montar(_cfg(tmp_path, lives), tmp_path)
    assert _por(linhas, evento_id="a__2026-10-14")[0]["particao"] == "test_prospectivo"


def test_ultimo_evento_de_cada_camera_vai_para_val(tmp_path):
    lives = [L("a", d, 15, "garoa") for d in (1, 2, 3)] + [L("a", 1, 16, "seco")]
    linhas, _ = ms.montar(_cfg(tmp_path, lives), tmp_path)
    assert {r["particao"] for r in _por(linhas, evento_id="a__2026-10-03")} == {"val"}
    assert {r["particao"] for r in _por(linhas, evento_id="a__2026-10-02")} == {"train"}


def test_camera_com_um_evento_so_fica_no_train(tmp_path):
    linhas, _ = ms.montar(_cfg(tmp_path, [L("b", 1, 15, "garoa"), L("b", 1, 16, "garoa")]), tmp_path)
    assert {r["particao"] for r in _por(linhas, camera="b")} == {"train"}


def test_camera_nao_verificada_sai_e_entra_no_resumo(tmp_path):
    lives = [L("a", 1, 15, "garoa"), L("b", 1, 15, "garoa")]
    linhas, resumo = ms.montar(_cfg(tmp_path, lives, verificadas=("a", "bc")), tmp_path)
    assert not _por(linhas, camera="b")
    assert resumo["excluidos"]["posicao_nao_verificada"] == 1


def test_referencia_por_periodo_e_tirada_das_outras_particoes(tmp_path):
    lives = [L("a", 1, h, "seco") for h in (13, 14, 15)] + [L("a", 2, 15, "garoa"), L("a", 3, 2, "garoa", periodo="noite")]
    linhas, resumo = ms.montar(_cfg(tmp_path, lives), tmp_path)
    refs = _por(linhas, particao="referencia", camera="a")
    assert len(refs) == 1
    ref_dia = refs[0]["caminho"]
    assert ref_dia.endswith("frame_1_14.jpg")            # mediana no tempo
    assert all(r["referencia"] == ref_dia for r in _por(linhas, camera="a") if r["particao"] != "referencia")
    assert resumo["referencias_faltando"] == []           # noite usou a do dia como reserva


def test_camera_sem_seco_fica_sem_referencia_e_aparece_no_resumo(tmp_path):
    linhas, resumo = ms.montar(_cfg(tmp_path, [L("b", 1, 15, "garoa")]), tmp_path)
    assert _por(linhas, camera="b")[0]["referencia"] == ""
    assert "b" in resumo["referencias_faltando"]


def test_5km_so_acrescenta_moderada_forte_sem_rotulo_estrito(tmp_path):
    lives = [L("a", 1, 15, "garoa"), L("a", 1, 16, "", motivo="poucas_estacoes_consenso"), L("a", 1, 17, "", motivo="x")]
    l5 = [L("a", 1, 15, "moderada"), L("a", 1, 16, "forte"), L("a", 1, 17, "garoa")]
    linhas, _ = ms.montar(_cfg(tmp_path, lives, l5=l5), tmp_path)
    assert {(r["caminho"].split("/")[-1], r["classe"], r["metodo_rotulo"]) for r in _por(linhas, camera="a")} == {
        ("frame_1_15.jpg", "garoa", "estacao"), ("frame_1_16.jpg", "forte", "raio_5km")}


def test_revisao_exclui_frames_marcados(tmp_path):
    rev = tmp_path / "revisao.csv"
    rev.write_text("pasta,arquivo,camera,classe,manifest,excluir,motivo\na,frame_1_15.jpg,a,garoa,m,1,congelada\n")
    linhas, resumo = ms.montar(_cfg(tmp_path, [L("a", 1, 15, "garoa"), L("a", 1, 16, "garoa")], revisao=str(rev)), tmp_path)
    assert [r["caminho"].split("/")[-1] for r in _por(linhas, camera="a")] == ["frame_1_16.jpg"]
    assert resumo["excluidos"]["revisao"] == 1


def test_ircnn_entra_com_caminho_da_raiz_e_particao_propria(tmp_path):
    ir = [{"caminho": "data/processed/ircnn/event_1/t1.jpg", "classe": "forte", "mm_h": "20", "evento_id": "ircnn__event_1", "periodo": "dia"},
          {"caminho": "data/processed/ircnn/event_1/t2.jpg", "classe": "seco", "mm_h": "0", "evento_id": "ircnn__event_1", "periodo": "dia"}]
    linhas, _ = ms.montar(_cfg(tmp_path, [L("a", 1, 15, "garoa")], ircnn=ir), tmp_path)
    r = _por(linhas, camera="ircnn", classe="forte")[0]
    assert r["caminho"] == "ml/data/processed/ircnn/event_1/t1.jpg" and r["particao"] == "ircnn" and r["origem"] == "irCNN"
    assert r["referencia"] == "ml/data/processed/ircnn/event_1/t2.jpg"


def test_teto_por_evento_e_classe_so_no_train(tmp_path):
    lives = [L("a", 1, h, "garoa") for h in range(10, 20)] + [L("a", 2, 15, "garoa")]
    cfg = _cfg(tmp_path, lives)
    cfg["max_por_evento_classe"] = 3
    linhas, _ = ms.montar(cfg, tmp_path)
    assert len(_por(linhas, evento_id="a__2026-10-01")) == 3
    assert len(_por(linhas, evento_id="a__2026-10-02")) == 1   # val não é cortado


def test_csv_tem_colunas_exatas(tmp_path):
    linhas, _ = ms.montar(_cfg(tmp_path, [L("a", 1, 15, "garoa")]), tmp_path)
    saida = tmp_path / "s.csv"
    ms.escrever(linhas, saida)
    with open(saida) as f:
        assert f.readline().strip() == ",".join(ms.COLUNAS)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_splits_fixa.py`
Expected: FAIL (script não existe).

- [ ] **Step 3: Implementar `ml/scripts/dataset/montar_splits_fixa.py`**

```python
#!/usr/bin/env python3
"""Splits do modelo de câmera fixa (spec CF4): por evento e por câmera, só dado real.

Partições:
  train / val       lives das câmeras de treino (último evento de cada câmera = val)
  ircnn             todos os eventos do irCNN; a CV por evento é feita no treino
  test_camera       a câmera de teste inteira, nunca vista no treino (Teste B)
  test_prospectivo  frames a partir do congelamento (Teste C)
  referencia        um `seco` por (câmera, período) usado como referência seca

Uso:
    ml/.venv/bin/python ml/scripts/dataset/montar_splits_fixa.py --config ml/configs/splits_fixa_v1.yaml
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paineis_revisao_fixa import ler_exclusoes  # noqa: E402

COLUNAS = ["caminho", "classe", "mm_h", "particao", "origem", "evento_id", "camera", "periodo", "ts_utc", "referencia", "metodo_rotulo"]


def _ts(r: dict) -> datetime | None:
    return datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")) if r.get("ts_utc") else None


def _ler(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def carregar_lives(manifest: Path, raiz_frames_rel: str, metodo_padrao: str = "") -> list[dict]:
    saida = []
    for r in _ler(manifest):
        if not r.get("classe"):
            continue
        saida.append({
            "caminho": f"{raiz_frames_rel}/{r['pasta']}/{r['arquivo']}", "classe": r["classe"], "mm_h": r.get("mm_h", ""),
            "particao": "", "origem": "live", "evento_id": r["evento_id"], "camera": r["pasta"],
            "periodo": r.get("periodo", ""), "ts_utc": r.get("ts_utc", ""), "referencia": "",
            "metodo_rotulo": r.get("metodo_rotulo") or metodo_padrao, "_pasta": r["pasta"], "_arquivo": r["arquivo"],
        })
    return saida


def acrescentar_5km(lives: list[dict], linhas_5km: list[dict], classes: set[str]) -> list[dict]:
    ja = {(r["_pasta"], r["_arquivo"]) for r in lives}
    extras = [dict(r, metodo_rotulo="raio_5km") for r in linhas_5km
              if r["classe"] in classes and (r["_pasta"], r["_arquivo"]) not in ja]
    return lives + extras


def carregar_ircnn(manifest: Path, prefixo: str) -> list[dict]:
    return [{
        "caminho": f"{prefixo}{r['caminho']}", "classe": r["classe"], "mm_h": r.get("mm_h", ""), "particao": "ircnn",
        "origem": "irCNN", "evento_id": r["evento_id"], "camera": "ircnn", "periodo": r.get("periodo", ""),
        "ts_utc": "", "referencia": "", "metodo_rotulo": "pluviometro_local", "_pasta": "ircnn", "_arquivo": r["caminho"],
    } for r in _ler(manifest) if r.get("classe")]


def escolher_referencias(linhas: list[dict], congelamento: datetime) -> dict[tuple[str, str], dict]:
    """Um `seco` por (câmera, período): o mediano no tempo (ou na ordem do caminho no irCNN)."""
    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in linhas:
        if r["classe"] != "seco":
            continue
        if r["origem"] == "live" and (_ts(r) is None or _ts(r) >= congelamento):
            continue
        grupos.setdefault((r["camera"], r["periodo"]), []).append(r)
    refs = {}
    for chave, rs in grupos.items():
        rs = sorted(rs, key=lambda r: (r["ts_utc"], r["caminho"]))
        refs[chave] = rs[len(rs) // 2]
    return refs


def atribuir_particoes(linhas: list[dict], camera_teste: str, congelamento: datetime) -> None:
    eventos_por_cam: dict[str, set[str]] = {}
    for r in linhas:
        if r["particao"]:
            continue
        if r["camera"] == camera_teste:
            r["particao"] = "test_camera"
        elif _ts(r) is not None and _ts(r) >= congelamento:
            r["particao"] = "test_prospectivo"
        else:
            eventos_por_cam.setdefault(r["camera"], set()).add(r["evento_id"])
    ultimo = {cam: max(evs) for cam, evs in eventos_por_cam.items() if len(evs) >= 2}
    for r in linhas:
        if not r["particao"]:
            r["particao"] = "val" if ultimo.get(r["camera"]) == r["evento_id"] else "train"


def limitar_por_evento_classe(linhas: list[dict], maximo: int) -> list[dict]:
    grupos: dict[tuple[str, str], list[dict]] = {}
    resto = []
    for r in linhas:
        (grupos.setdefault((r["evento_id"], r["classe"]), []) if r["particao"] == "train" else resto).append(r)
    saida = list(resto)
    for chave in sorted(grupos):
        rs = sorted(grupos[chave], key=lambda r: (r["ts_utc"], r["caminho"]))
        if len(rs) > maximo:
            idx = np.linspace(0, len(rs) - 1, maximo).round().astype(int)
            rs = [rs[i] for i in idx]
        saida.extend(rs)
    return saida


def montar(cfg: dict, raiz: Path) -> tuple[list[dict], dict]:
    congelamento = datetime.fromisoformat(cfg["congelamento_utc"].replace("Z", "+00:00"))
    excluidos = Counter()

    lives = carregar_lives(Path(cfg["manifest_lives"]), cfg["raiz_frames_lives"])
    if cfg.get("manifest_lives_5km"):
        l5 = carregar_lives(Path(cfg["manifest_lives_5km"]), cfg["raiz_frames_lives"])
        lives = acrescentar_5km(lives, l5, set(cfg.get("classes_5km", ["moderada", "forte"])))

    if cfg.get("exigir_posicao_verificada", True):
        fontes = yaml.safe_load(Path(cfg["coleta_fixa_config"]).read_text())["fontes"]
        ok = {f["id"] for f in fontes if f.get("posicao_verificada")}
        antes = len(lives)
        lives = [r for r in lives if r["camera"] in ok]
        excluidos["posicao_nao_verificada"] = antes - len(lives)

    exclusoes = ler_exclusoes(Path(cfg["revisao_csv"])) if cfg.get("revisao_csv") else set()
    antes = len(lives)
    lives = [r for r in lives if (r["_pasta"], r["_arquivo"]) not in exclusoes]
    excluidos["revisao"] = antes - len(lives)

    linhas = lives + carregar_ircnn(Path(cfg["manifest_ircnn"]), cfg.get("prefixo_ircnn", "ml/"))

    refs = escolher_referencias(linhas, congelamento)
    ids_ref = {id(r) for r in refs.values()}
    for r in refs.values():
        r["particao"] = "referencia"
    faltando = set()
    for r in linhas:
        if id(r) in ids_ref:
            continue
        outro = "noite" if r["periodo"] == "dia" else "dia"
        ref = refs.get((r["camera"], r["periodo"])) or refs.get((r["camera"], outro))
        r["referencia"] = ref["caminho"] if ref else ""
        if not ref:
            faltando.add(r["camera"])

    atribuir_particoes(linhas, cfg["camera_teste"], congelamento)
    linhas = limitar_por_evento_classe(linhas, int(cfg.get("max_por_evento_classe", 200)))
    linhas.sort(key=lambda r: (r["particao"], r["camera"], r["ts_utc"], r["caminho"]))

    resumo = {
        "por_particao_classe": {p: dict(Counter(r["classe"] for r in linhas if r["particao"] == p))
                                for p in sorted({r["particao"] for r in linhas})},
        "por_camera": {c: dict(Counter(r["particao"] for r in linhas if r["camera"] == c))
                       for c in sorted({r["camera"] for r in linhas})},
        "eventos_por_particao": {p: len({r["evento_id"] for r in linhas if r["particao"] == p})
                                 for p in sorted({r["particao"] for r in linhas})},
        "excluidos": dict(excluidos),
        "referencias_faltando": sorted(faltando),
        "congelamento_utc": cfg["congelamento_utc"],
    }
    return linhas, resumo


def escrever(linhas: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLUNAS, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(linhas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/splits_fixa_v1.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    cfg = {k: (str(RAIZ / v) if k.startswith(("manifest_", "coleta_fixa_config", "revisao_csv")) and v else v) for k, v in cfg.items()}
    linhas, resumo = montar(cfg, RAIZ)
    escrever(linhas, RAIZ / cfg["saida"])
    (RAIZ / cfg["resumo"]).write_text(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Atenção ao mapear caminhos relativos no `main`: `manifest_lives_5km` e `revisao_csv` podem estar vazios; o comprehension acima só prefixa quando há valor.

`ml/configs/splits_fixa_v1.yaml`:

```yaml
# Splits do modelo de câmera fixa (spec CF4). Só dado real; nada de sintético.
saida: ml/data/splits/fixa_v1.csv
resumo: ml/data/splits/fixa_v1_resumo.json

manifest_lives: ml/data/manifests/manifest_coleta_fixa.csv
# CF3.2: moderada/forte rotuladas por consenso a 5 km, só depois da revisão visual
manifest_lives_5km: ml/data/manifests/manifest_coleta_fixa_5km.csv
classes_5km: [moderada, forte]
raiz_frames_lives: ml/data/raw/coleta_fixa

manifest_ircnn: ml/data/manifests/manifest_ircnn.csv
prefixo_ircnn: "ml/"   # caminhos do manifest do irCNN são relativos a ml/

coleta_fixa_config: ml/configs/coleta_fixa.yaml
exigir_posicao_verificada: true
revisao_csv: ml/data/review/camera_fixa/revisao.csv

camera_teste: bc_atlantica            # Teste B: nunca vista no treino
congelamento_utc: "2026-10-13T00:00:00Z"   # Teste C: tudo daqui em diante é prospectivo
max_por_evento_classe: 200
```

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_splits_fixa.py ml/tests/test_paineis_revisao.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/dataset/montar_splits_fixa.py ml/configs/splits_fixa_v1.yaml ml/tests/test_splits_fixa.py
git commit -m "feat(dataset): splits do modelo fixo por evento e câmera, com referência seca"
```

---

### Task 5 [ORQUESTRADOR + HUMANO]: Execução dos dados

Esta tarefa **não** vai para subagente: precisa de rede, da cota do CEMADEN e de olho humano. O orquestrador roda os comandos com o Rodrigo presente e de dia (o Mac não fica ligado à noite).

- [ ] **Step 1 (HUMANO) — CF1.1 posição das câmeras.** Para cada fonte ativa em `coleta_fixa.yaml`, abrir a live, achar o ponto no Google Maps pelo que aparece na imagem, corrigir `lat`/`lon` e marcar `posicao_verificada: true`; preencher `fonte_publica` com a página que publica a câmera.
- [ ] **Step 2 — CF1.3 Santos e Praia Grande sem rótulo.** Conferir quantas estações cada câmera tem a ≤ 2 km e ≤ 5 km:

```bash
ml/.venv/bin/python - <<'E'
import csv, yaml, sys
sys.path.insert(0, "ml/scripts/estacoes")
from distancia import haversine_km
fontes = yaml.safe_load(open("ml/configs/coleta_fixa.yaml"))["fontes"]
est = {}
for r in csv.DictReader(open("ml/data/raw/estacoes/normalizado/cemaden_ped.csv")):
    est[r["estacao_id"]] = (float(r["lat"]), float(r["lon"]))
for f in fontes:
    d = sorted(haversine_km(f["lat"], f["lon"], la, lo) for la, lo in est.values())
    print(f["id"], "≤2km:", sum(x <= 2 for x in d), "≤5km:", sum(x <= 5 for x in d), "mais perto: %.1f km" % d[0])
E
```

Se faltar estação, acrescentar em `ESTACOES_COLETA_FIXA` de `baixar_cemaden_ped.py` (códigos do feed `resources.cemaden.gov.br/dados/311_24.json`). Commit `feat(estacoes): estações CEMADEN de <cidade>`.
- [ ] **Step 3 — Cadastrar as câmeras no backend** (depois do Plano A em produção), uma por fonte verificada, com o nome `fixa-<id>`:

```bash
curl -s -X POST "$API/api/v1/devices/" -H "Authorization: Bearer $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"fixa-sp_centro_geolan","tipo":"fixa","latitude":-23.5465,"longitude":-46.6340,"stream_url":"https://www.youtube.com/watch?v=dJN7snkYg-I","descricao":"Centro de SP"}'
```

Guardar cada `api_key` em `ml/configs/coleta_fixa_tokens.json` (gitignored). Nunca colar a admin key em arquivo.
- [ ] **Step 4 — Colheita (repetir a cada 2 dias até 18/10):**

```bash
ml/.venv/bin/pip install -U yt-dlp
ml/.venv/bin/python ml/scripts/estacoes/baixar_cemaden_ped.py --dias $(date -v-2d +%F) $(date -v-1d +%F) $(date +%F)
caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --onde-choveu --desde <ISO da última colheita>
caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --modo-seco --passo-s 300 --desde <ISO da última colheita>
ml/.venv/bin/python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa.yaml
ml/.venv/bin/python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa_5km.yaml
```

Anotar o ISO da colheita no fim de `docs/COMO-CONTINUAR.md` (seção nova "Colheitas da câmera fixa").
- [ ] **Step 5 (HUMANO) — Revisão visual:**

```bash
ml/.venv/bin/python ml/scripts/dataset/paineis_revisao_fixa.py \
  --manifest ml/data/manifests/manifest_coleta_fixa.csv --manifest ml/data/manifests/manifest_coleta_fixa_5km.csv
open ml/data/review/camera_fixa
```

Rodrigo marca `excluir=1` + `motivo` no `revisao.csv` só para defeito de imagem.
- [ ] **Step 6 — Splits:** `ml/.venv/bin/python ml/scripts/dataset/montar_splits_fixa.py`. Conferir o resumo: cada câmera de treino com `seco` e alguma chuva; `referencias_faltando` vazio (senão, voltar ao Step 4 com `--modo-seco` naquela câmera); irCNN com as 4 classes.
- [ ] **Step 7 — Commit dos manifests** (eles são versionados; pixels não):

```bash
git add ml/data/manifests/manifest_coleta_fixa*.csv ml/data/manifests/manifest_coleta_fixa*_relatorio.json ml/configs/coleta_fixa.yaml
git commit -m "data: manifests da câmera fixa (colheita até <data>)"
```

- [ ] **Step 8 — Teste C (18/10):** última colheita, revisão e `montar_splits_fixa.py`. Registrar no `resumo` a data de congelamento e não mexer mais no modelo depois de olhar o `test_prospectivo`.

---

### Task 6 (opcional, P1): Enviar leituras de pluviômetro ao backend

Par do Plano A Task 8. Só fazer se o A8 for feito.

**Files:**
- Create: `ml/scripts/estacoes/enviar_leituras.py`
- Test: `ml/tests/test_enviar_leituras.py`

**Interfaces:**
- `leituras_perto_das_cameras(leituras: list[dict], fontes: list[dict], raio_km: float = 5.0, desde: datetime | None = None) -> list[dict]` — só estações a ≤ `raio_km` de alguma câmera; `ts_utc` ≥ `desde`.
- CLI: `enviar_leituras.py --desde <ISO> --api <url>`; usa `ADMIN_KEY` do ambiente; POST em lotes de 500 para `/api/v1/estacoes/leituras`.

- [ ] **Step 1:** teste com 3 estações (uma a 1 km, uma a 4 km, uma a 30 km de uma câmera) e leituras antes/depois de `desde` → só as duas próximas, só depois de `desde`.
- [ ] **Step 2:** ver falhar; **Step 3:** implementar (reusar `haversine_km` de `distancia.py`); **Step 4:** ver passar; **Step 5:** commit `feat(estacoes): envia leituras de pluviômetro perto das câmeras ao backend`.
