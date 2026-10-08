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
    rev = _revisao(tmp_path, ["a,frame_1_16.jpg,a,forte,l5.csv,,\n"])  # 5 km só entra revisado
    linhas, _ = ms.montar(_cfg(tmp_path, lives, l5=l5, revisao=rev), tmp_path)
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


def _revisao(tmp_path, linhas):
    rev = tmp_path / "revisao.csv"
    rev.write_text("pasta,arquivo,camera,classe,manifest,excluir,motivo\n" + "".join(linhas))
    return str(rev)


def _caminhos_5km(linhas):
    return {r["caminho"].split("/")[-1] for r in linhas if r["metodo_rotulo"] == "raio_5km"}


def test_5km_sem_manifest_nao_quebra_e_e_ignorado(tmp_path, capsys):
    cfg = _cfg(tmp_path, [L("a", 1, 15, "garoa")])
    cfg["manifest_lives_5km"] = str(tmp_path / "nao_existe_5km.csv")
    linhas, resumo = ms.montar(cfg, tmp_path)
    assert len(_por(linhas, camera="a")) == 1
    assert "5km" in capsys.readouterr().out


def test_5km_sem_revisao_e_descartado_e_contado(tmp_path):
    lives = [L("a", 1, 15, "garoa")]
    l5 = [L("a", 1, 16, "forte"), L("a", 1, 17, "moderada")]
    linhas, resumo = ms.montar(_cfg(tmp_path, lives, l5=l5), tmp_path)
    assert _caminhos_5km(linhas) == set()
    assert resumo["excluidos"]["5km_sem_revisao"] == 2


def test_5km_revisado_por_camera_e_classe_entra(tmp_path):
    lives = [L("a", 1, 15, "garoa")]
    l5 = [L("a", 1, 16, "forte"), L("a", 1, 17, "moderada"), L("b", 1, 16, "forte")]
    # revisão do manifest 5 km só cobre (a, forte); a revisão de OUTRO manifest não vale
    rev = _revisao(tmp_path, ["a,frame_1_16.jpg,a,forte,l5.csv,,\n", "a,frame_1_17.jpg,a,moderada,lives.csv,,\n"])
    linhas, resumo = ms.montar(_cfg(tmp_path, lives, l5=l5, revisao=rev), tmp_path)
    assert _caminhos_5km(linhas) == {"frame_1_16.jpg"}
    assert resumo["excluidos"]["5km_sem_revisao"] == 2
    assert resumo["por_metodo_rotulo"] == {"estacao": 1, "raio_5km": 1}
