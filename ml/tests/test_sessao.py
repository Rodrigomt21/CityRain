"""Testes do diagnóstico de sessão (J6): sessao.py e a extensão de
verifica_teste_campo.py.

Motivação registrada em docs/specs/spec-pipeline-jetson.md (J6): hoje a
diferença entre "a energia caiu" e "alguém apertou o botão" só é descoberta
cruzando arquivos de 0 byte com o `wtmp` e com `orphan inode` do ext4 —
arqueologia manual que não escala pra uma temporada de coleta inteira. Estes
testes cobrem o parsing puro (com amostras reais desta placa), o ciclo
boot/marcador/CSV, e o resumo retroativo por sessão sobre dado real de
campo (23/09).
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Mesmo padrão de test_normalizacao.py / test_uploader.py: os scripts vivem
# fora de um pacote Python instalável, então são carregados direto do
# arquivo pelo caminho.


def _carrega(nome_modulo: str, caminho_relativo: str):
    caminho = Path(__file__).resolve().parents[1] / caminho_relativo
    spec = importlib.util.spec_from_file_location(nome_modulo, caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


sessao = _carrega("sessao", "scripts/captura/sessao.py")
verifica = _carrega("verifica_teste_campo", "scripts/captura/verifica_teste_campo.py")


# ---------------------------------------------------------------------------
# Amostras reais desta placa (ver docs/specs/spec-pipeline-jetson.md, seção
# "Testabilidade" do J6 e Apêndice A).
# ---------------------------------------------------------------------------

DMESG_COM_ORPHAN = "EXT4-fs (sda1): 11 orphan inodes deleted\nEXT4-fs (sda1): recovery complete\n"

WTMP_CRASH = (
    "jetson   :0           :0               Wed Sep 23 09:49 - crash  (-9762+11:49)\n"
    "runlevel (to lvl 5)   4.9.299-tegra    Tue Sep 15 22:23 - 09:50 (7+11:26)\n"
    "shutdown system down  4.9.299-tegra    Tue Sep 15 22:23 - 23:00 (-9755+00:22)\n"
)

WTMP_LIMPO = (
    "shutdown system down  4.9.299-tegra    Tue Sep 15 22:23:05 2026 - Fri Dec 31 23:00:13 1999 (-9755+00:22)\n"
    "runlevel (to lvl 5)   4.9.299-tegra    Tue Sep 15 21:07:04 2026 - Tue Sep 15 22:23:05 2026  (01:16)\n"
    "jetson   :0           :0               Tue Sep 15 21:07:00 2026 - down                      (01:16)\n"
)


# ---------------------------------------------------------------------------
# 1. Parsing puro de orphan inodes.
# ---------------------------------------------------------------------------


def test_conta_orphan_inodes_amostra_real():
    assert sessao.conta_orphan_inodes(DMESG_COM_ORPHAN) == 11


def test_conta_orphan_inodes_sem_ocorrencia():
    assert sessao.conta_orphan_inodes("EXT4-fs (sda1): mounted filesystem\n") == 0


def test_conta_orphan_inodes_soma_multiplas_linhas():
    texto = DMESG_COM_ORPHAN + "EXT4-fs (sda1): 4 orphan inodes deleted\n"
    assert sessao.conta_orphan_inodes(texto) == 15


# ---------------------------------------------------------------------------
# 2. Parsing puro de wtmp — só o tipo do evento mais recente importa, nunca
#    a hora (sem RTC, ela pode estar errada).
# ---------------------------------------------------------------------------


def test_ultimo_evento_wtmp_crash():
    assert sessao.ultimo_evento_wtmp(WTMP_CRASH) == "crash"


def test_ultimo_evento_wtmp_limpo():
    assert sessao.ultimo_evento_wtmp(WTMP_LIMPO) == "limpo"


def test_ultimo_evento_wtmp_vazio_ou_sem_padrao_conhecido():
    assert sessao.ultimo_evento_wtmp("") is None
    assert sessao.ultimo_evento_wtmp("linha qualquer sem sentido\n") is None


# ---------------------------------------------------------------------------
# 3. hora_rmc_utc: segunda fonte de tempo, tolerante à ausência.
# ---------------------------------------------------------------------------


def test_le_hora_gps_arquivo_ausente(tmp_path):
    assert sessao.le_hora_gps(str(tmp_path / "nao_existe.json")) is None


def test_le_hora_gps_campo_ausente(tmp_path):
    """Schema antigo (pré-J7), ainda em produção nesta Jetson agora — o
    campo simplesmente não existe no dict."""
    caminho = tmp_path / "gps.json"
    caminho.write_text('{"fix": false, "latitude": null}')
    assert sessao.le_hora_gps(str(caminho)) is None


def test_le_hora_gps_json_corrompido(tmp_path):
    caminho = tmp_path / "gps.json"
    caminho.write_text("")
    assert sessao.le_hora_gps(str(caminho)) is None


def test_le_hora_gps_presente(tmp_path):
    caminho = tmp_path / "gps.json"
    caminho.write_text('{"fix": true, "hora_rmc_utc": "2026-09-23T09:49:28+00:00"}')
    assert sessao.le_hora_gps(str(caminho)) == "2026-09-23T09:49:28+00:00"


# ---------------------------------------------------------------------------
# 4. Ciclo completo boot/marcador/CSV, com dmesg/wtmp/relógio injetados —
#    nenhum destes testes toca em dmesg/last/relógio real.
# ---------------------------------------------------------------------------


def _agora_fixo(iso: str):
    dt = datetime.fromisoformat(iso)
    return lambda: dt


def test_primeiro_boot_sem_marcador_e_limpo(tmp_path):
    sessao_dir = str(tmp_path / "sessao")
    linha = sessao.registra_boot(
        sessao_dir=sessao_dir,
        gps_json_path=str(tmp_path / "gps_inexistente.json"),
        dmesg_fn=lambda: "",
        wtmp_fn=lambda: "",
        agora_fn=_agora_fixo("2026-09-23T09:49:28+00:00"),
    )
    assert linha["tipo"] == "limpo"
    assert linha["marcador_sessao_anterior"] == "false"
    assert linha["orphan_inodes"] == "0"
    assert linha["boot_utc_gps"] == ""
    assert sessao.marcador_existe(sessao_dir), "boot tem que recriar o marcador pro próximo ciclo"


def test_marcador_sobrevivente_vira_crash(tmp_path):
    sessao_dir = str(tmp_path / "sessao")
    # Simula uma sessão anterior que nunca chegou ao ExecStop (corte real).
    sessao.cria_marcador(sessao_dir)

    linha = sessao.registra_boot(
        sessao_dir=sessao_dir,
        gps_json_path=str(tmp_path / "gps_inexistente.json"),
        dmesg_fn=lambda: DMESG_COM_ORPHAN,
        wtmp_fn=lambda: WTMP_CRASH,
        agora_fn=_agora_fixo("2026-09-23T09:58:51+00:00"),
    )
    assert linha["tipo"] == "crash"
    assert linha["marcador_sessao_anterior"] == "true"
    assert linha["orphan_inodes"] == "11"
    assert linha["wtmp_ultimo_evento"] == "crash"


def test_stop_remove_marcador_proximo_boot_e_limpo(tmp_path):
    """O ciclo completo: boot cria o marcador; stop (ExecStop, desligamento
    ordenado) remove; o boot seguinte não vê marcador ⇒ limpo."""
    sessao_dir = str(tmp_path / "sessao")

    sessao.registra_boot(
        sessao_dir=sessao_dir,
        gps_json_path=str(tmp_path / "gps_inexistente.json"),
        dmesg_fn=lambda: "",
        wtmp_fn=lambda: "",
        agora_fn=_agora_fixo("2026-09-15T21:07:00+00:00"),
    )
    assert sessao.marcador_existe(sessao_dir)

    sessao.remove_marcador(sessao_dir)
    assert not sessao.marcador_existe(sessao_dir)

    linha = sessao.registra_boot(
        sessao_dir=sessao_dir,
        gps_json_path=str(tmp_path / "gps_inexistente.json"),
        dmesg_fn=lambda: "",
        wtmp_fn=lambda: WTMP_LIMPO,
        agora_fn=_agora_fixo("2026-09-15T22:23:05+00:00"),
    )
    assert linha["tipo"] == "limpo"
    assert linha["marcador_sessao_anterior"] == "false"


def test_boots_csv_e_append_only_e_sobrevive_a_reboot(tmp_path):
    """Duas chamadas de registra_boot (dois "boots" em processos
    separados, como aconteceria de verdade) têm de resultar em duas linhas,
    cabeçalho uma vez só — e o arquivo é lido de volta como um CSV comum,
    prova de que sobrevive à "reinicialização" (aqui, à criação de uma nova
    instância do módulo não muda nada — o estado vive só no arquivo)."""
    sessao_dir = str(tmp_path / "sessao")

    sessao.registra_boot(
        sessao_dir=sessao_dir,
        gps_json_path=str(tmp_path / "gps_inexistente.json"),
        dmesg_fn=lambda: "",
        wtmp_fn=lambda: "",
        agora_fn=_agora_fixo("2026-09-15T21:07:00+00:00"),
    )
    # Sem remove_marcador() entre os dois: simula que esta sessão nunca
    # chegou ao ExecStop (corte de energia) — o próximo boot tem de ver o
    # marcador da primeira chamada ainda lá.
    sessao.registra_boot(
        sessao_dir=sessao_dir,
        gps_json_path=str(tmp_path / "gps_inexistente.json"),
        dmesg_fn=lambda: DMESG_COM_ORPHAN,
        wtmp_fn=lambda: WTMP_CRASH,
        agora_fn=_agora_fixo("2026-09-23T09:58:51+00:00"),
    )

    caminho_csv = Path(sessao_dir) / sessao.CSV_NOME_PADRAO
    with open(caminho_csv, newline="") as f:
        conteudo = f.read()
    assert conteudo.count("boot_utc_sistema") == 1, "cabeçalho só na primeira vez"

    linhas = sessao.le_boots_csv(sessao_dir)
    assert len(linhas) == 2
    assert linhas[0]["tipo"] == "limpo"
    assert linhas[1]["tipo"] == "crash"
    assert linhas[1]["orphan_inodes"] == "11"


def test_le_boots_csv_sem_arquivo_devolve_lista_vazia(tmp_path):
    assert sessao.le_boots_csv(str(tmp_path / "nao_existe")) == []


# ---------------------------------------------------------------------------
# 5. Restrição de linguagem (Python 3.6.9 na Jetson): guarda de regressão
#    simples contra sintaxe 3.7+ escapar despercebida num commit futuro.
#    A validação de verdade é compilar contra o interpretador real da placa
#    (ver comando no relatório) — isto aqui é só um alarme rápido local.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caminho_relativo", ["scripts/captura/sessao.py"])
def test_sem_sintaxe_python37_mais_recente(caminho_relativo):
    texto = (Path(__file__).resolve().parents[1] / caminho_relativo).read_text()
    assert ":=" not in texto, "walrus operator não existe no Python 3.6.9 da Jetson"
    assert "from __future__ import annotations" not in texto
    assert "dataclass" not in texto


# ---------------------------------------------------------------------------
# 6. Teste retroativo real (aceite do J6): rodar a lógica sobre a sessão de
#    23/09 e reportar os 3 cortes e os 63 pares inválidos.
#
# Os frames ficam em ml/data/raw/imt_coleta/cityrain_frames4/ — pasta de
# dados de campo, gitignorada (ver .gitignore: ml/data/raw/**). Em qualquer
# checkout que não tenha essa cópia local (ex.: clone limpo), o teste é
# pulado em vez de falhar.
# ---------------------------------------------------------------------------

_FRAMES4 = Path(__file__).resolve().parents[1] / "data" / "raw" / "imt_coleta" / "cityrain_frames4"


@pytest.mark.skipif(not _FRAMES4.is_dir(), reason="cityrain_frames4 não está presente neste checkout (dado gitignorado)")
def test_retroativo_sessao_23_09_reporta_3_cortes_e_63_invalidos():
    """Ver Apêndice A da spec: sessão de 23/09 (09:49–10:06), 305 frames,
    63 pares de 0 byte, 3 cortes de energia (503s, 135s, 106s), ~744s
    parada (72% da sessão) e **rendimento ponta a ponta de ~23,8%** — o
    número que a spec manda citar, não a taxa de perda (20,7%) sozinha."""
    inicio = datetime(2026, 9, 23, 9, 49, 0)
    fim = datetime(2026, 9, 23, 10, 7, 0)

    resumo = verifica.resumo_sessao(inicio, frames_dir=str(_FRAMES4), fim=fim)

    assert resumo["frames_capturados"] == 305
    assert resumo["pares_invalidos"] == 63
    assert resumo["frames_validos"] == 242
    assert resumo["cortes_detectados"] == 3
    assert resumo["taxa_perda"] == pytest.approx(63 / 305, abs=1e-9)

    duracoes = sorted(c[2] for c in resumo["cortes_detalhe"])
    assert duracoes[0] == pytest.approx(105.924, abs=0.5)
    assert duracoes[1] == pytest.approx(135.363, abs=0.5)
    assert duracoes[2] == pytest.approx(503.198, abs=0.5)

    # Tolerância, não igualdade exata: a cadência medida varia um pouco
    # conforme quais deltas "normais" entram na mediana.
    assert resumo["tempo_parado_s"] == pytest.approx(744, abs=5)
    assert resumo["fracao_parada"] == pytest.approx(0.72, abs=0.02)
    assert resumo["cadencia_mediana_s"] == pytest.approx(1.02, abs=0.05)
    assert resumo["rendimento_ponta_a_ponta"] == pytest.approx(0.238, abs=0.02)
    # A distinção que motivou a extensão: rendimento é bem pior que
    # "1 - taxa_perda" porque conta o tempo parado, não só os bytes vazios.
    assert resumo["rendimento_ponta_a_ponta"] < 1 - resumo["taxa_perda"]


def test_rendimento_capta_prejuizo_que_taxa_de_perda_esconde(tmp_path):
    """Sessão sintética adversarial: TODOS os pares escritos são íntegros
    (taxa de perda 0%), mas a maior parte do tempo foi gasta num corte —
    exatamente o alerta do coordenador: taxa de perda baixa não implica
    rendimento bom, porque ela nunca vê o tempo em que nada foi escrito.
    """
    pasta = tmp_path / "frames"
    pasta.mkdir()

    def grava_par(dt, jpg=b"\xff\xd8\xff" + b"x", metadado=None):
        nome = dt.strftime("frame_%Y%m%d_%H%M%S_") + f"{dt.microsecond // 1000:03d}"
        (pasta / f"{nome}.jpg").write_bytes(jpg)
        (pasta / f"{nome}.json").write_text("{}" if metadado is None else metadado)

    inicio_sessao = datetime(2026, 1, 1, 12, 0, 0)
    # 5 frames a 1s de cadência, um corte de 60s, mais 5 frames a 1s.
    from datetime import timedelta

    for i in range(5):
        grava_par(inicio_sessao + timedelta(seconds=i))
    for i in range(5):
        grava_par(inicio_sessao + timedelta(seconds=4 + 60 + 1 + i))

    resumo = verifica.resumo_sessao(inicio_sessao, frames_dir=str(pasta))

    assert resumo["pares_invalidos"] == 0
    assert resumo["taxa_perda"] == 0.0
    assert resumo["cortes_detectados"] == 1
    # Rendimento tem de denunciar o prejuízo que a taxa de perda (0%) esconde.
    assert resumo["rendimento_ponta_a_ponta"] is not None
    assert resumo["rendimento_ponta_a_ponta"] < 0.2
