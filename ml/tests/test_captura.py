"""Testes da escrita durável de frame+metadado do captura.py (J1).

Motivação registrada em docs/specs/spec-pipeline-jetson.md (J1): sem `fsync`,
um corte de energia em campo deixa o par jpg+json com nome final e 0 byte — o
nome já foi pro journal do ext4, o conteúdo ainda estava em página suja na
RAM. Medido em 2026-09-23: 63 de 305 frames (21%) assim numa única sessão.
Estes testes provam que, depois da mudança, o nome final só passa a existir
quando o conteúdo (e, no fim do ciclo, o próprio rename) já está no disco.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

# `captura.py` importa `cv2`, que não existe neste venv (só na Jetson) e abre
# a câmera / entra num `while True` ao ser executado como script. Stub do cv2
# antes de carregar o módulo — mesmo padrão de test_uploader.py (stuba `gate`)
# — e carregamento por caminho — mesmo padrão de test_normalizacao.py, já que
# `ml/scripts/captura/` não é um pacote instalável.
#
# O stub replica um detalhe do cv2 REAL que já mordeu esta spec uma vez:
# `imwrite`/`imencode` escolhem o codificador pela extensão recebida (do
# caminho, no caso do imwrite; do parâmetro `ext`, no caso do imencode) e
# levantam `cv2.error` — que NÃO herda de `IOError` — pra extensão
# desconhecida (confirmado com OpenCV 3.2.0 na própria Jetson: `imwrite` num
# caminho terminado em `.tmp` levanta `could not find a writer for the
# specified extension`). Um stub que ignorasse isso (como o `lambda: True`
# anterior) deixaria passar batido exatamente o bug que esta suíte existe pra
# pegar — teste verde não é evidência quando o stub decide o comportamento
# que devia estar sob teste.
JPEG_MAGIC = b"\xff\xd8\xff"
_EXTENSOES_SUPORTADAS = (".jpg", ".jpeg", ".png")


class _FakeVideoCapture:
    """Nunca deveria ser instanciada nestes testes: os helpers exercitados
    aqui não abrem câmera. Existe só pra `main()` ser importável sem quebrar,
    caso algum teste futuro precise dela."""

    def __init__(self, *a, **k):
        self._aberta = True

    def isOpened(self):
        return self._aberta

    def set(self, *a, **k):
        pass

    def read(self):
        return False, None

    def release(self):
        self._aberta = False


def _fake_imencode(ext, frame):
    """Simula `cv2.imencode`: sucesso devolve `(True, buffer)` com um buffer
    que tem `.tobytes()` (como o `numpy.ndarray` real — `bytes`/`bytearray`
    puros NÃO têm esse método, por isso o `memoryview` aqui); extensão não
    reconhecida levanta `cv2.error`, nunca retorna `False`."""
    if ext not in _EXTENSOES_SUPORTADAS:
        raise _cv2_stub.error(
            "could not find a writer for the specified extension (simulado): {!r}".format(ext)
        )
    return True, memoryview(JPEG_MAGIC + b"conteudo-fake")


def _fake_imwrite(caminho, frame):
    """Simula `cv2.imwrite`: reproduz o bug real — o codificador é escolhido
    pela extensão do CAMINHO, então `frame_1.jpg.tmp` (extensão `.tmp`) tem
    que falhar aqui, mesmo que o `frame_1.jpg` final funcionasse."""
    ext = os.path.splitext(caminho)[1]
    if ext not in _EXTENSOES_SUPORTADAS:
        raise _cv2_stub.error(
            "could not find a writer for the specified extension (simulado): {!r}".format(caminho)
        )
    Path(caminho).write_bytes(JPEG_MAGIC + b"conteudo-fake")
    return True


class _CvError(Exception):
    """Equivalente ao `cv2.error` real: uma `Exception` comum, sem relação
    nenhuma com `IOError`/`OSError` (confirmado na Jetson via `.__mro__`)."""


_cv2_stub = types.ModuleType("cv2")
_cv2_stub.CAP_PROP_FRAME_HEIGHT = 4
_cv2_stub.VideoCapture = _FakeVideoCapture
_cv2_stub.error = _CvError
_cv2_stub.imencode = _fake_imencode
_cv2_stub.imwrite = _fake_imwrite
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "captura" / "captura.py"
)
_spec = importlib.util.spec_from_file_location("captura", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
cap = importlib.util.module_from_spec(_spec)
# O stub vale só durante o carregamento de `captura.py` (que guarda a
# referência em `cap.cv2`). Deixá-lo em `sys.modules` quebrava os testes do
# gerador sintético e da régua, que usam o cv2 real instalado no venv.
_cv2_original = sys.modules.get("cv2")
sys.modules["cv2"] = _cv2_stub
try:
    _spec.loader.exec_module(cap)
finally:
    if _cv2_original is None:
        del sys.modules["cv2"]
    else:
        sys.modules["cv2"] = _cv2_original


# ---------------------------------------------------------------------------
# _grava_duravel: o mecanismo genérico por trás de jpg e json.
# ---------------------------------------------------------------------------


def test_grava_duravel_produz_arquivo_final_e_nao_deixa_tmp(tmp_path):
    final = tmp_path / "frame_1.jpg"

    cap._grava_duravel(str(final), lambda tmp: Path(tmp).write_bytes(b"conteudo"))

    assert final.read_bytes() == b"conteudo"
    assert not (tmp_path / "frame_1.jpg.tmp").exists()


def test_grava_duravel_chama_fsync_antes_do_rename(tmp_path, monkeypatch):
    """O fsync tem de acontecer enquanto o arquivo ainda está com o nome
    .tmp — se rodasse depois do rename, o corte de energia entre o rename e
    o fsync ainda deixaria uma janela sem garantia nenhuma."""
    final = tmp_path / "frame_1.json"
    tmp_esperado = tmp_path / "frame_1.json.tmp"
    chamadas = []

    fsync_original = cap.os.fsync

    def fsync_espiao(fd):
        # Nesse ponto o .tmp já deve existir e o final ainda não.
        chamadas.append((tmp_esperado.exists(), final.exists()))
        return fsync_original(fd)

    monkeypatch.setattr(cap.os, "fsync", fsync_espiao)

    cap._grava_duravel(str(final), lambda tmp: Path(tmp).write_text("{}"))

    assert chamadas == [(True, False)]
    assert final.exists()


def test_grava_duravel_nao_promove_arquivo_se_fsync_falha(tmp_path, monkeypatch):
    """Se o fsync do conteúdo falhar, o rename nunca deve rodar — a sobra
    admissível é só o .tmp, nunca um nome final sem garantia."""
    final = tmp_path / "frame_1.jpg"

    def fsync_com_falha(fd):
        raise OSError("disco cheio, simulado")

    monkeypatch.setattr(cap.os, "fsync", fsync_com_falha)

    with pytest.raises(OSError):
        cap._grava_duravel(str(final), lambda tmp: Path(tmp).write_bytes(b"x"))

    assert not final.exists()
    assert (tmp_path / "frame_1.jpg.tmp").exists()


def test_grava_duravel_propaga_erro_de_escrita_sem_criar_final(tmp_path):
    """Se a própria escrita falhar (ex.: cv2.imwrite reportando falha), o
    nome final não pode existir."""
    final = tmp_path / "frame_1.jpg"

    def escreve_com_falha(tmp):
        raise IOError("falha simulada de escrita")

    with pytest.raises(IOError):
        cap._grava_duravel(str(final), escreve_com_falha)

    assert not final.exists()


# ---------------------------------------------------------------------------
# _fsync_diretorio: fsync do diretório, pro rename em si não se perder.
# ---------------------------------------------------------------------------


def test_fsync_diretorio_nao_levanta_erro(tmp_path):
    cap._fsync_diretorio(str(tmp_path))


def test_fsync_diretorio_chama_os_fsync(tmp_path, monkeypatch):
    chamadas = []
    fsync_original = cap.os.fsync

    def fsync_espiao(fd):
        chamadas.append(fd)
        return fsync_original(fd)

    monkeypatch.setattr(cap.os, "fsync", fsync_espiao)
    cap._fsync_diretorio(str(tmp_path))

    assert len(chamadas) == 1


# ---------------------------------------------------------------------------
# salva_frame_duravel: wrapper de _grava_duravel em cima de cv2.imencode.
#
# Regressão coberta aqui: uma versão anterior chamava `cv2.imwrite(tmp,
# frame)` com `tmp = caminho_final + ".tmp"`. Como o `imwrite` real escolhe o
# codificador pela extensão do NOME do arquivo, isso levantava `cv2.error`
# em toda chamada (extensão efetiva `.tmp`, não `.jpg`) — confirmado com o
# OpenCV 3.2.0 real da Jetson. `salva_frame_duravel` tem que evitar esse
# problema de raiz: `cv2.imencode(".jpg", frame)` decide o formato por um
# parâmetro fixo, nunca pelo nome do arquivo, então o sufixo `.tmp` do
# caminho intermediário deixa de importar pro cv2.
# ---------------------------------------------------------------------------


def test_salva_frame_duravel_grava_jpg_sem_deixar_tmp(tmp_path):
    caminho_jpg = tmp_path / "frame_20260928_120000_000.jpg"
    cap.salva_frame_duravel(str(caminho_jpg), "frame-fake")

    assert caminho_jpg.read_bytes().startswith(JPEG_MAGIC)
    assert not (tmp_path / (caminho_jpg.name + ".tmp")).exists()


def test_salva_frame_duravel_nao_chama_imwrite(tmp_path, monkeypatch):
    """Trava de regressão: se alguém reintroduzir `cv2.imwrite(tmp, frame)`
    no meio do caminho, este teste falha antes de chegar na Jetson — o
    `imwrite` fake aqui simula fielmente a extensão-define-o-codec e
    levantaria `cv2.error` para o `.tmp`."""

    def imwrite_nao_deveria_ser_chamado(caminho, frame):
        raise AssertionError(
            "salva_frame_duravel não deveria chamar cv2.imwrite — "
            "o caminho intermediário termina em .tmp, e o imwrite real "
            "escolhe o codec pela extensão do nome do arquivo"
        )

    monkeypatch.setattr(cap.cv2, "imwrite", imwrite_nao_deveria_ser_chamado)

    caminho_jpg = tmp_path / "frame_1.jpg"
    cap.salva_frame_duravel(str(caminho_jpg), "frame-fake")  # não deve levantar

    assert caminho_jpg.exists()


def test_regressao_imwrite_com_sufixo_tmp_falha_por_extensao(tmp_path):
    """Documenta o bug em si (fora do caminho de produção): `cv2.imwrite`
    aplicado a um caminho `frame_1.jpg.tmp` levanta `cv2.error`, enquanto o
    mesmo conteúdo em `frame_1.jpg` funciona — prova de que o problema é
    puramente a extensão do nome, não o conteúdo nem o frame."""
    caminho_com_tmp = tmp_path / "frame_1.jpg.tmp"
    with pytest.raises(cap.cv2.error):
        cap.cv2.imwrite(str(caminho_com_tmp), "frame-fake")
    assert not caminho_com_tmp.exists()

    caminho_final = tmp_path / "frame_1.jpg"
    assert cap.cv2.imwrite(str(caminho_final), "frame-fake") is True
    assert caminho_final.exists()


def test_salva_frame_duravel_propaga_cv2_error_sem_criar_jpg_final(tmp_path, monkeypatch):
    """Falha real de codificação (`cv2.imencode` levantando `cv2.error`, não
    devolvendo `False`) não pode deixar o `.jpg` final aparecer."""
    def imencode_com_falha(ext, frame):
        raise cap.cv2.error("falha de codificação simulada")

    monkeypatch.setattr(cap.cv2, "imencode", imencode_com_falha)

    caminho_jpg = tmp_path / "frame_1.jpg"
    with pytest.raises(cap.cv2.error):
        cap.salva_frame_duravel(str(caminho_jpg), "frame-fake")

    assert not caminho_jpg.exists()
    assert not (tmp_path / "frame_1.jpg.tmp").exists()


def test_salva_frame_duravel_levanta_ioerror_se_imencode_retorna_false(tmp_path, monkeypatch):
    """Caso `cv2.imencode` reporte falha "educadamente" (`ok=False`, sem
    levantar), `salva_frame_duravel` converte isso num erro explícito em vez
    de gravar um jpg vazio/corrompido."""
    monkeypatch.setattr(cap.cv2, "imencode", lambda ext, frame: (False, None))

    caminho_jpg = tmp_path / "frame_1.jpg"
    with pytest.raises(IOError):
        cap.salva_frame_duravel(str(caminho_jpg), "frame-fake")

    assert not caminho_jpg.exists()


# ---------------------------------------------------------------------------
# salva_metadado_duravel: wrapper de _grava_duravel em cima de json.dump.
# ---------------------------------------------------------------------------


def test_salva_metadado_duravel_grava_json_legivel_sem_deixar_tmp(tmp_path):
    caminho_json = tmp_path / "frame_20260928_120000_000.json"
    metadado = {
        "schema": 2,
        "device_id": "jetson-nano-01",
        "capturado_em_utc": "2026-09-28T12:00:00+00:00",
        "arquivo": "frame_20260928_120000_000.jpg",
        "gps": None,
    }

    cap.salva_metadado_duravel(str(caminho_json), metadado)

    with open(caminho_json) as f:
        assert json.load(f) == metadado
    assert not (tmp_path / (caminho_json.name + ".tmp")).exists()


# ---------------------------------------------------------------------------
# main(): um ciclo completo do laço grava o par na ordem certa e faz o
# fsync do diretório, sem executar de fato (loop é interrompido de propósito
# depois de 1 frame).
# ---------------------------------------------------------------------------


class _EncerraLaco(Exception):
    """Usada só pra sair do `while True` de `main()` de forma controlada,
    como se a câmera tivesse parado de responder para sempre."""


def test_main_um_ciclo_grava_par_completo_e_fsync_do_diretorio(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "FRAMES_DIR", str(tmp_path))
    monkeypatch.setattr(cap.time, "sleep", lambda s: None)
    # Usa o `cv2.imencode` padrão do stub (realista: sucesso pra ".jpg") —
    # nenhum monkeypatch de codificação necessário aqui.

    chamadas_fsync_dir = []
    fsync_dir_original = cap._fsync_diretorio

    def fsync_dir_espiao(caminho):
        chamadas_fsync_dir.append(caminho)
        return fsync_dir_original(caminho)

    monkeypatch.setattr(cap, "_fsync_diretorio", fsync_dir_espiao)

    class _FakeCap:
        def __init__(self):
            self.leituras = 0
            self.liberada = False

        def isOpened(self):
            return True

        def set(self, *a, **k):
            pass

        def read(self):
            self.leituras += 1
            if self.leituras > 1:
                raise _EncerraLaco()
            return True, "frame-fake"

        def release(self):
            self.liberada = True

    fake_cap_instancia = _FakeCap()
    monkeypatch.setattr(cap.cv2, "VideoCapture", lambda idx: fake_cap_instancia)

    with pytest.raises(_EncerraLaco):
        cap.main()

    jpgs = sorted(tmp_path.glob("frame_*.jpg"))
    jsons = sorted(tmp_path.glob("frame_*.json"))
    tmps = list(tmp_path.glob("*.tmp"))

    assert len(jpgs) == 1
    assert len(jsons) == 1
    assert tmps == []
    assert chamadas_fsync_dir == [str(tmp_path)]

    with open(jsons[0]) as f:
        metadado = json.load(f)
    assert metadado["arquivo"] == jpgs[0].name
    assert metadado["schema"] == 2

    # cap.release() tem de rodar mesmo quando o laço sai por exceção — é o
    # `finally` de main() garantindo isso.
    assert fake_cap_instancia.liberada is True


def test_main_cv2_error_no_meio_da_gravacao_nao_derruba_o_laco(tmp_path, monkeypatch):
    """O caso que motivou este pedido de correção: uma falha de codificação
    levanta `cv2.error`, que NÃO é `IOError`. Se `main()` só capturasse
    `IOError`, essa exceção escaparia do laço, matando o processo — e como
    `citycam.service` tem `Restart=always`, a Jetson entraria em crash-loop
    sem capturar frame nenhum. Este teste prova que o primeiro frame (que
    falha) é logado e pulado, e o laço segue vivo pro segundo frame (que dá
    certo)."""
    monkeypatch.setattr(cap, "FRAMES_DIR", str(tmp_path))
    monkeypatch.setattr(cap.time, "sleep", lambda s: None)

    chamadas_imencode = []
    imencode_original = cap.cv2.imencode

    def imencode_falha_na_primeira(ext, frame):
        chamadas_imencode.append(ext)
        if len(chamadas_imencode) == 1:
            raise cap.cv2.error("falha de codificação simulada (1º frame)")
        return imencode_original(ext, frame)

    monkeypatch.setattr(cap.cv2, "imencode", imencode_falha_na_primeira)

    class _FakeCap:
        def __init__(self):
            self.leituras = 0
            self.liberada = False

        def isOpened(self):
            return True

        def set(self, *a, **k):
            pass

        def read(self):
            self.leituras += 1
            if self.leituras > 2:
                raise _EncerraLaco()
            return True, "frame-fake"

        def release(self):
            self.liberada = True

    fake_cap_instancia = _FakeCap()
    monkeypatch.setattr(cap.cv2, "VideoCapture", lambda idx: fake_cap_instancia)

    # Se cv2.error escapasse do laço, seria essa exceção (não _EncerraLaco)
    # que se propagaria daqui — o pytest.raises abaixo reprovaria o teste.
    with pytest.raises(_EncerraLaco):
        cap.main()

    assert len(chamadas_imencode) == 2  # tentou os dois frames, não morreu no 1º

    jpgs = sorted(tmp_path.glob("frame_*.jpg"))
    jsons = sorted(tmp_path.glob("frame_*.json"))
    tmps = list(tmp_path.glob("*.tmp"))

    # Só o 2º frame (o que não falhou) deixou par completo; o 1º não deixou
    # nem .jpg nem sobra de .tmp.
    assert len(jpgs) == 1
    assert len(jsons) == 1
    assert tmps == []
    assert fake_cap_instancia.liberada is True
