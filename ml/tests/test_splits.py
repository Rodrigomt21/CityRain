"""Testes do montar_splits (D3) com manifests fictícios pequenos."""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "scripts" / "dataset" / "montar_splits.py"
_spec = importlib.util.spec_from_file_location("montar_splits", _P)
assert _spec is not None and _spec.loader is not None
ms = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ms
_spec.loader.exec_module(ms)

RAIZ = Path(__file__).resolve().parents[2]
EV01, EV13, EV04, EV06 = (
    "cityrain_frames2__2026-09-01", "cityrain_frames3__2026-09-13",
    "cityrain_frames__2026-08-04", "cityrain_frames2__2026-08-07",
)
CFG = {
    "utc_offset_h": -3, "imagens_dir": "ml/data/processed/imt_coleta", "stride_s": 2,
    "intensidade": [
        {"particao": "train", "evento_id": EV01, "classe": "garoa", "local_ate": "08:38:00", "stride": True},
        {"particao": "val", "evento_id": EV01, "classe": "garoa", "local_desde": "08:40:00", "stride": False},
        {"particao": "test_real", "evento_id": EV13, "classe": "garoa", "stride": False},
    ],
    "ordinal_2309": {"particao": "test_ordinal_2309", "pasta": "cityrain_frames4",
                     "data_local": "2026-09-23", "rotulo_fraco": ">=garoa"},
    "gate_seco": [
        {"particao": "train", "evento_id": EV04, "classe": "seco", "stride": True},
        {"particao": "test", "evento_id": EV06, "classe": "seco", "stride": False},
    ],
}


def _lin(pasta, evento, local: str, classe, i=0, periodo="dia"):
    """Frame com horário local 'YYYY-MM-DD HH:MM:SS' (+ i segundos)."""
    t = datetime.fromisoformat(local) + timedelta(seconds=i) + timedelta(hours=3)
    return {"arquivo": f"f_{local[:10]}_{local[11:].replace(':', '')}_{i}.jpg", "pasta": pasta,
            "evento_id": evento, "ts_utc": t.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "mm_h": "1.2" if classe == "garoa" else "0.0", "classe": classe,
            "motivo_exclusao": "", "periodo": periodo}


def _imt():
    r = []
    # 01/09: 08:37:50 .. 08:38:10 (1 fps) e 08:39:50 .. 08:40:10
    r += [_lin("cityrain_frames2", EV01, "2026-09-01 08:37:50", "garoa", i) for i in range(21)]
    r += [_lin("cityrain_frames2", EV01, "2026-09-01 08:39:50", "garoa", i) for i in range(21)]
    r += [_lin("cityrain_frames3", EV13, "2026-09-13 10:00:00", "garoa", i) for i in range(5)]
    r += [_lin("cityrain_frames", EV04, "2026-08-04 08:00:00", "seco", i) for i in range(10)]
    r += [_lin("cityrain_frames2", EV06, "2026-08-06 20:00:00", "seco", i, "noite") for i in range(3)]
    r += [_lin("cityrain_frames4", "", "2026-09-23 09:00:00", "", i) for i in range(4)]
    r += [_lin("cityrain_frames4", "", "2026-09-16 20:00:00", "", i, "noite") for i in range(2)]
    return r


def _ext():
    ir = [{"caminho": "ml/data/processed/ircnn/e/t1.jpg", "classe": "forte", "mm_h": "20",
           "evento_id": "ircnn__e", "periodo": "dia"}]
    yt = [{"caminho": "data/processed/youtube/f/a.jpg", "classe": "", "evento_id": "youtube__f",
           "trecho": "unico", "rotulo_fraco": ">=moderada"}]
    return ir, yt


def test_bloco_temporal_01_09():
    linhas, _ = ms.montar_intensidade(CFG, _imt(), *_ext())
    def hora(l):
        nome = Path(l["caminho"]).name  # f_2026-09-01_083750_0.jpg
        return datetime.strptime(nome.split("_")[2], "%H%M%S").time() , int(nome.split("_")[3][:-4])
    tr = [l for l in linhas if l["particao"] == "train"]
    va = [l for l in linhas if l["particao"] == "val"]
    assert tr and va
    for l in va:
        base, i = hora(l)
        t = (datetime.combine(datetime.min, base) + timedelta(seconds=i)).time()
        assert t >= datetime.strptime("08:40:00", "%H:%M:%S").time()
    for l in tr:
        base, i = hora(l)
        t = (datetime.combine(datetime.min, base) + timedelta(seconds=i)).time()
        assert t < datetime.strptime("08:38:00", "%H:%M:%S").time()


def test_stride_2s():
    linhas, sess = ms.montar_intensidade(CFG, _imt(), *_ext())
    s = sess[f"{EV01}:train"]
    assert s["antes_stride"] == 10 and s["depois_stride"] == 5  # 08:37:50..59, 1 fps
    assert sess[f"{EV01}:val"]["depois_stride"] == sess[f"{EV01}:val"]["antes_stride"] == 11


def test_evento_unico_por_particao_exceto_0109():
    linhas, _ = ms.montar_intensidade(CFG, _imt(), *_ext())
    por_ev: dict[str, set[str]] = {}
    for l in linhas:
        por_ev.setdefault(l["evento_id"], set()).add(l["particao"])
    for ev, ps in por_ev.items():
        if ev != EV01:
            assert len(ps) == 1, ev
    assert por_ev[EV01] == {"train", "val"}


def test_2309_so_ordenacao_e_sem_classe():
    linhas, _ = ms.montar_intensidade(CFG, _imt(), *_ext())
    o = [l for l in linhas if l["particao"] == "test_ordinal_2309"]
    assert len(o) == 4  # 16/09 fica de fora
    assert all(l["classe"] == "" and l["mm_h"] == "" and l["rotulo_fraco"] == ">=garoa" for l in o)
    assert all(l["origem"] == "real" for l in o)


def test_externos_e_caminhos_da_raiz():
    linhas, _ = ms.montar_intensidade(CFG, _imt(), *_ext())
    yt = [l for l in linhas if l["particao"] == "test_ordinal_youtube"][0]
    assert yt["caminho"] == "ml/data/processed/youtube/f/a.jpg" and yt["trecho"] == "unico"
    assert [l for l in linhas if l["particao"] == "test_ircnn"][0]["origem"] == "irCNN"
    assert not any(l["classe"] == "seco" for l in linhas)


def _sint(base, n=1):
    return [{"caminho": f"ml/data/synthetic/x/{i}.jpg", "classe": "forte", "mm_h_alvo": "30",
             "base_frame": base, "seed": str(i)} for i in range(n)]


def test_sinteticos_so_em_train():
    imt = _imt()
    base = [l for l in imt if l["evento_id"] == EV01][0]
    ok = f"{base['pasta']}/{base['arquivo']}"
    linhas, _ = ms.montar_intensidade(CFG, imt, *_ext(), sinteticos=_sint(ok, 2))
    sint = [l for l in linhas if l["origem"] == "sintetico"]
    assert len(sint) == 2 and all(l["particao"] == "train" for l in sint)


def test_sintetico_com_base_fora_do_train_e_recusado():
    imt = _imt()
    val = [l for l in imt if l["evento_id"] == EV01][-1]  # 08:40:10 -> val
    for ruim in (f"{val['pasta']}/{val['arquivo']}", "cityrain_frames3/inexistente.jpg"):
        with pytest.raises(ValueError):
            ms.montar_intensidade(CFG, imt, *_ext(), sinteticos=_sint(ruim))


def test_gate():
    linhas, sess = ms.montar_gate(CFG, _imt())
    c = {(l["particao"], l["classe"]) for l in linhas}
    assert c == {("train", "chuva"), ("val", "chuva"), ("test_real", "chuva"), ("train", "seco"), ("test", "seco")}
    assert sess[f"{EV04}:train"] == {"antes_stride": 10, "depois_stride": 5}
    assert all(l["periodo"] == "noite" for l in linhas if l["particao"] == "test")


def test_determinismo_e_resumo():
    a, _ = ms.montar_intensidade(CFG, _imt(), *_ext())
    b, _ = ms.montar_intensidade(CFG, list(reversed(_imt())), *_ext())
    assert a == b
    assert ms.resumo(a)["test_real"]["garoa"]["real"] == 5


def test_existencia_de_caminhos(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    ms.verificar_existencia([{"caminho": "a.jpg"}], tmp_path)
    with pytest.raises(FileNotFoundError):
        ms.verificar_existencia([{"caminho": "b.jpg"}], tmp_path)


def test_csv_gerado_no_repo():
    """Se o CSV real existe, valida os invariantes de aceite sobre ele."""
    caminho = RAIZ / "ml/data/splits/intensidade_v1.csv"
    if not caminho.exists():
        pytest.skip("rode montar_splits.py antes")
    with open(caminho, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    por_ev: dict[str, set[str]] = {}
    for l in linhas:
        por_ev.setdefault(l["evento_id"], set()).add(l["particao"])
        if l["origem"] == "sintetico":
            # Regra da spec: sintético nunca em teste (train e val podem ter).
            assert l["particao"] in ("train", "val")
    for ev, ps in por_ev.items():
        if ev != EV01:
            assert len(ps) == 1, ev
    # horários de 01/09 o nome do frame já está em hora local
    for l in linhas:
        if l["evento_id"] == EV01:
            h = datetime.strptime(Path(l["caminho"]).stem[6:21], "%Y%m%d_%H%M%S")
            if l["particao"] == "val":
                assert h.time() >= datetime.strptime("08:40:00", "%H:%M:%S").time()
            else:
                assert h.time() < datetime.strptime("08:38:00", "%H:%M:%S").time()


def test_sinteticos_de_val_exigem_base_em_val():
    imt = _imt()
    ev01 = [l for l in imt if l["evento_id"] == EV01]
    em_val = f"{ev01[-1]['pasta']}/{ev01[-1]['arquivo']}"      # 08:40:10 -> val
    em_train = f"{ev01[0]['pasta']}/{ev01[0]['arquivo']}"      # 08:37:50 -> train
    linhas, sess = ms.montar_intensidade(CFG, imt, *_ext(), sinteticos_val=_sint(em_val, 3))
    sint = [l for l in linhas if l["origem"] == "sintetico"]
    assert len(sint) == 3 and all(l["particao"] == "val" for l in sint)
    assert sess["sinteticos:val"]["depois_stride"] == 3
    with pytest.raises(ValueError):
        ms.montar_intensidade(CFG, imt, *_ext(), sinteticos_val=_sint(em_train))


def test_exclusao_por_trecho_coberto():
    cfg = {**CFG, "exclusoes": [
        {"evento_id": EV01, "local_desde": "08:39:55", "local_ate": "08:40:05", "motivo": "garagem"},
    ]}
    imt = _imt()
    dentro = [l for l in imt if l["evento_id"] == EV01 and ms._excluido(l, cfg)]
    assert len(dentro) == 11  # 08:39:55..08:40:05, limites inclusivos, 1 fps
    assert {ms._excluido(l, cfg) for l in dentro} == {"garagem"}
    # Outra sessão no mesmo horário não é afetada.
    assert not ms._excluido({**dentro[0], "evento_id": EV13}, cfg)
    assert not any(ms._excluido(l, CFG) for l in imt)  # sem `exclusoes`, nada sai
