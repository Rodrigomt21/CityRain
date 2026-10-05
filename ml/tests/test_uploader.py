"""Testes da validação de par e da quarentena do uploader (J2).

Motivação registrada em docs/specs/spec-pipeline-jetson.md (J2): corte de
energia em campo produz pares jpg+json com nome final e conteúdo vazio. Antes
desta guarda, um json de 0 byte fazia `json.load` levantar `JSONDecodeError`
fora de qualquer `try`, o processo morria, `Restart=always` reiniciava e
`pares_pendentes()` devolvia o mesmo par primeiro — fila travada
indefinidamente. Medido em 2026-09-28: 63 pares assim numa única sessão.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

# `uploader.py` importa `gate`, que por sua vez importa o detector treinado de
# ~/modelo_chuva (só existe na Jetson). Stub antes de carregar o módulo: estes
# testes exercitam a validação de par, que não toca no modelo.
_gate_stub = types.ModuleType("gate")
_gate_stub.CLASSE_COM_GOTA = "com_gota"
_gate_stub.CLASSE_SEM_GOTA = "sem_gota"
_gate_stub.classificar = lambda *a, **k: {"classe": "sem_gota", "probabilidade": 0.0}
sys.modules.setdefault("gate", _gate_stub)

# Mesmo padrão do test_normalizacao.py: o script vive fora de um pacote Python
# instalável, então o módulo é carregado direto do arquivo pelo caminho.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "captura" / "uploader.py"
)
_spec = importlib.util.spec_from_file_location("uploader", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
up = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(up)


JPEG_MAGIC = b"\xff\xd8\xff"
METADADO_OK = {
    "schema": 2,
    "device_id": "jetson-nano-01",
    "capturado_em_utc": "2026-09-23T12:49:28.725509+00:00",
    "arquivo": "frame_20260923_094928_718.jpg",
    "gps": {"fix": False, "latitude": None, "longitude": None},
}


def cria_par(pasta: Path, nome: str, *, jpg: bytes, metadado) -> tuple[Path, Path]:
    """Escreve um par jpg+json. `metadado` None grava json vazio; str grava cru."""
    caminho_jpg = pasta / f"{nome}.jpg"
    caminho_json = pasta / f"{nome}.json"
    caminho_jpg.write_bytes(jpg)
    if metadado is None:
        caminho_json.write_bytes(b"")
    elif isinstance(metadado, str):
        caminho_json.write_text(metadado)
    else:
        caminho_json.write_text(json.dumps(metadado))
    return caminho_jpg, caminho_json


def test_par_integro_passa(tmp_path):
    jpg, js = cria_par(tmp_path, "ok", jpg=JPEG_MAGIC + b"conteudo", metadado=METADADO_OK)
    assert up.par_invalido(str(jpg), str(js)) is None


def test_jpg_de_zero_byte(tmp_path):
    jpg, js = cria_par(tmp_path, "z", jpg=b"", metadado=METADADO_OK)
    assert up.par_invalido(str(jpg), str(js)) == "jpg de 0 byte"


def test_json_de_zero_byte(tmp_path):
    """O caso real observado em campo: ambos os arquivos vazios."""
    jpg, js = cria_par(tmp_path, "z", jpg=b"", metadado=None)
    # o jpg é checado primeiro, então o motivo reportado é o dele
    assert up.par_invalido(str(jpg), str(js)) == "jpg de 0 byte"

    jpg2, js2 = cria_par(tmp_path, "z2", jpg=JPEG_MAGIC + b"x", metadado=None)
    assert up.par_invalido(str(jpg2), str(js2)) == "json de 0 byte"


def test_jpg_sem_magic_bytes(tmp_path):
    jpg, js = cria_par(tmp_path, "n", jpg=b"nao sou jpeg", metadado=METADADO_OK)
    assert up.par_invalido(str(jpg), str(js)) == "jpg sem magic bytes de JPEG"


def test_json_truncado(tmp_path):
    jpg, js = cria_par(tmp_path, "t", jpg=JPEG_MAGIC + b"x", metadado='{"schema": 2, "dev')
    assert up.par_invalido(str(jpg), str(js)).startswith("ilegivel:")


def test_arquivo_ausente_nao_levanta(tmp_path):
    """Par pode desaparecer entre a listagem e a validação (o próprio uploader
    move arquivos). Isso é motivo de pular, não de derrubar o processo."""
    motivo = up.par_invalido(str(tmp_path / "nao_existe.jpg"), str(tmp_path / "nao_existe.json"))
    assert motivo is not None and motivo.startswith("ilegivel:")


def test_quarentena_move_os_dois_e_registra(tmp_path):
    fila = tmp_path / "frames"
    fila.mkdir()
    quarentena = tmp_path / "par_invalido"
    jpg, js = cria_par(fila, "frame_20260923_100313_675", jpg=b"", metadado=None)
    config = {"pasta_par_invalido": str(quarentena)}

    up.move_para_par_invalido(str(jpg), str(js), "jpg de 0 byte", config)

    assert not jpg.exists() and not js.exists(), "par deveria sair da fila"
    assert (quarentena / jpg.name).exists(), "jpg deveria estar na quarentena"
    assert (quarentena / js.name).exists(), "json deveria estar na quarentena"

    with open(quarentena / up.AUDITORIA_INVALIDOS) as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == 1
    assert linhas[0]["arquivo"] == jpg.name
    assert linhas[0]["motivo"] == "jpg de 0 byte"
    assert linhas[0]["detectado_em_utc"]


def test_auditoria_acumula_sem_repetir_cabecalho(tmp_path):
    fila = tmp_path / "frames"
    fila.mkdir()
    quarentena = tmp_path / "par_invalido"
    config = {"pasta_par_invalido": str(quarentena)}
    for i in range(3):
        jpg, js = cria_par(fila, f"f{i}", jpg=b"", metadado=None)
        up.move_para_par_invalido(str(jpg), str(js), "jpg de 0 byte", config)

    with open(quarentena / up.AUDITORIA_INVALIDOS) as f:
        conteudo = f.read()
    assert conteudo.count("detectado_em_utc") == 1, "cabeçalho só na primeira vez"
    with open(quarentena / up.AUDITORIA_INVALIDOS) as f:
        assert len(list(csv.DictReader(f))) == 3


def test_nada_e_apagado_pela_quarentena(tmp_path):
    """A spec exige que par inválido seja movido, nunca removido — ele é a
    evidência de que houve corte de energia naquele instante."""
    fila = tmp_path / "frames"
    fila.mkdir()
    quarentena = tmp_path / "par_invalido"
    jpg, js = cria_par(fila, "f", jpg=b"", metadado=None)
    up.move_para_par_invalido(str(jpg), str(js), "jpg de 0 byte", {"pasta_par_invalido": str(quarentena)})
    assert len(list(quarentena.glob("*.jpg"))) == 1
    assert len(list(quarentena.glob("*.json"))) == 1


def test_regressao_o_bug_do_crash_loop(tmp_path):
    """Documenta o bug que o J2 conserta.

    `carrega_metadado` num json vazio levanta — era isso que derrubava o
    processo. A guarda tem de interceptar ANTES, devolvendo motivo em vez de
    deixar a exceção escapar.
    """
    jpg, js = cria_par(tmp_path, "vazio", jpg=JPEG_MAGIC + b"x", metadado=None)

    with pytest.raises(ValueError):
        up.carrega_metadado(str(js))

    assert up.par_invalido(str(jpg), str(js)) == "json de 0 byte"


def test_pares_pendentes_ignora_tmp(tmp_path, monkeypatch):
    """Arquivos .tmp são restos de escrita interrompida (o padrão tmp+rename do
    captura.py) e não podem entrar na fila."""
    monkeypatch.setattr(up, "FRAMES_DIR", str(tmp_path))
    cria_par(tmp_path, "bom", jpg=JPEG_MAGIC + b"x", metadado=METADADO_OK)
    (tmp_path / "frame_parcial.json.tmp").write_text("{}")
    (tmp_path / "frame_parcial.jpg").write_bytes(JPEG_MAGIC)

    nomes = [Path(j).name for _, j in up.pares_pendentes()]
    assert nomes == ["bom.json"]


# --- J3: nunca apagar o único registro local de um frame de campo ---------
#
# Motivação (spec-pipeline-jetson.md, J3): apaga_par() removia jpg+json após
# um 2xx do backend. Em regime permanente faz sentido, mas numa sessão de
# coleta é perigoso — se o backend aceitar um payload com schema errado, ou
# perder o dado depois do 2xx, o frame já não existe em lugar nenhum. Com
# `modo_coleta: true`, o par confirmado é preservado em
# frames/enviados/AAAAMMDD/ em vez de removido.


def test_apaga_par_modo_producao_remove(tmp_path):
    """Comportamento padrão (modo_coleta ausente/false) é preservado: apaga."""
    jpg, js = cria_par(tmp_path, "ok", jpg=JPEG_MAGIC + b"x", metadado=METADADO_OK)
    up.apaga_par(str(jpg), str(js), {"modo_coleta": False})
    assert not jpg.exists() and not js.exists()


def test_apaga_par_modo_coleta_preserva_em_enviados(tmp_path):
    """Com modo_coleta=true, o par some de `frames/` mas aparece íntegro em
    frames/enviados/AAAAMMDD/ — nunca é removido do disco."""
    fila = tmp_path / "frames"
    fila.mkdir()
    enviados = tmp_path / "frames" / "enviados"
    jpg, js = cria_par(fila, "frame_20260913_101500_000", jpg=JPEG_MAGIC + b"x", metadado=METADADO_OK)
    config = {"modo_coleta": True, "pasta_enviados": str(enviados)}

    up.apaga_par(str(jpg), str(js), config)

    assert not jpg.exists() and not js.exists(), "par deve sair de frames/"

    pasta_do_dia = enviados / "20260913"
    assert (pasta_do_dia / jpg.name).exists(), "jpg deveria estar em frames/enviados/AAAAMMDD/"
    assert (pasta_do_dia / js.name).exists(), "json deveria estar em frames/enviados/AAAAMMDD/"
    # conteúdo íntegro, não só o nome
    assert (pasta_do_dia / jpg.name).read_bytes() == JPEG_MAGIC + b"x"


def test_move_para_enviados_nao_apaga_nada(tmp_path):
    """Mesmo espírito do teste de quarentena do J2: nada é removido, só movido."""
    fila = tmp_path / "frames"
    fila.mkdir()
    enviados = tmp_path / "frames" / "enviados"
    jpg, js = cria_par(fila, "frame_20260905_120000_500", jpg=JPEG_MAGIC + b"x", metadado=METADADO_OK)

    up.move_para_enviados(str(jpg), str(js), {"pasta_enviados": str(enviados)})

    assert len(list((enviados / "20260905").glob("*.jpg"))) == 1
    assert len(list((enviados / "20260905").glob("*.json"))) == 1


def test_apaga_par_usa_data_de_captura_nao_de_envio(tmp_path):
    """O bug que motivou esta correção: a fila real da Jetson tem pares de
    sessões antigas (05/09, 13/09, 15/09, 23/09 — 1.713 pares verificados em
    28/09/2026). Se a subpasta usasse a data de HOJE (quando a fila drena),
    todas essas sessões distintas cairiam juntas em enviados/20260928/,
    anulando o propósito de separar por sessão de coleta. A subpasta tem de
    vir da data de captura embutida no nome do arquivo, não de `datetime.now()`
    no momento do envio."""
    fila = tmp_path / "frames"
    fila.mkdir()
    enviados = tmp_path / "frames" / "enviados"
    jpg, js = cria_par(fila, "frame_20260923_094928_718", jpg=JPEG_MAGIC + b"x", metadado=METADADO_OK)

    up.apaga_par(str(jpg), str(js), {"modo_coleta": True, "pasta_enviados": str(enviados)})

    hoje = datetime.now().strftime("%Y%m%d")
    assert (enviados / "20260923" / jpg.name).exists(), "tem de ir pra pasta da data de CAPTURA"
    if hoje != "20260923":
        assert not (enviados / hoje).exists(), "não pode criar pasta da data de HOJE"


def test_pares_de_dias_diferentes_vao_para_subpastas_distintas(tmp_path):
    """Reproduz o cenário real relatado: pares de quatro sessões diferentes
    (05/09, 13/09, 15/09, 23/09) processados na mesma execução do uploader
    têm de se separar em quatro subpastas — nunca se misturar numa só."""
    fila = tmp_path / "frames"
    fila.mkdir()
    enviados = tmp_path / "frames" / "enviados"
    config = {"modo_coleta": True, "pasta_enviados": str(enviados)}

    datas_esperadas = ["20260905", "20260913", "20260915", "20260923"]
    pares = [
        cria_par(fila, f"frame_{data}_120000_{i:03d}", jpg=JPEG_MAGIC + str(i).encode(), metadado=METADADO_OK)
        for i, data in enumerate(datas_esperadas)
    ]

    for jpg, js in pares:
        up.apaga_par(str(jpg), str(js), config)

    assert {p.name for p in enviados.iterdir()} == set(datas_esperadas)
    for jpg, _ in pares:
        data = jpg.name.split("_")[1]
        assert (enviados / data / jpg.name).exists()


def test_data_sessao_nome_fora_do_padrao_cai_no_fallback_e_avisa(tmp_path, capsys):
    """Frame com nome fora do contrato frame_AAAAMMDD_HHMMSS_mmm (legado,
    renomeado manualmente etc.) não pode fazer a função inventar uma data
    errada em silêncio — cai pra hoje, mas avisa no log, porque isso indica
    que uma premissa do módulo mudou."""
    assert up.data_sessao("/qualquer/legado_sem_timestamp.jpg") == datetime.now().strftime("%Y%m%d")
    saida = capsys.readouterr().out
    assert "fora do padrão" in saida
    assert "legado_sem_timestamp.jpg" in saida


def test_pares_pendentes_ignora_frames_enviados(tmp_path, monkeypatch):
    """Critério de aceite do J3: frames/enviados/ tem de ser ignorado por
    pares_pendentes(), senão o uploader reenvia em loop o que já enviou.
    Confirmado aqui com teste (não só lendo o código): pares_pendentes() usa
    os.listdir (não recursivo) em FRAMES_DIR, então arquivos dentro de uma
    subpasta nunca chegam a entrar no `set` de candidatos."""
    monkeypatch.setattr(up, "FRAMES_DIR", str(tmp_path))

    # par pendente de verdade, direto em FRAMES_DIR
    cria_par(tmp_path, "pendente", jpg=JPEG_MAGIC + b"x", metadado=METADADO_OK)

    # par já confirmado e preservado por uma sessão anterior em modo_coleta
    pasta_enviados_hoje = tmp_path / "enviados" / "20260928"
    pasta_enviados_hoje.mkdir(parents=True)
    cria_par(pasta_enviados_hoje, "ja_enviado", jpg=JPEG_MAGIC + b"y", metadado=METADADO_OK)

    nomes = [Path(j).name for _, j in up.pares_pendentes()]
    assert nomes == ["pendente.json"], "par já enviado não pode reentrar na fila"


def test_mensagem_modo_reflete_config():
    """O modo em vigor tem de aparecer, sem ambiguidade, no log de arranque."""
    msg_coleta = up.mensagem_modo({"modo_coleta": True})
    msg_producao = up.mensagem_modo({"modo_coleta": False})
    msg_ausente = up.mensagem_modo({})

    assert "modo_coleta=true" in msg_coleta
    assert "enviados" in msg_coleta
    assert "modo_coleta=false" in msg_producao
    assert "modo_coleta=false" in msg_ausente, "ausência do campo equivale a false"
