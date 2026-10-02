"""Testes do script de rotulagem frame -> classe de chuva (F1.3).

Usa frames e leituras de estação sintéticos, com coordenadas e intensidades
escolhidas para exercitar cada regra do plano: raio máximo, janela centrada,
zona morta nas fronteiras e determinismo da saída. Ver docs/plano-dataset.md.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

# Mesmo padrão do test_normalizacao.py: o script vive fora de um pacote Python
# instalável, então o módulo é carregado direto do arquivo pelo caminho.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "rotulagem" / "gerar_manifest.py"
)
_spec = importlib.util.spec_from_file_location("gerar_manifest", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
rot = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rot
_spec.loader.exec_module(rot)


# Estação de referência e um ponto a ~100 m dela (0,001° de latitude ~= 111 m).
EST_LAT, EST_LON = -23.5500, -46.6300
PERTO_LAT, PERTO_LON = -23.5491, -46.6300
T0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def _serie(valores_por_offset: dict[int, float]) -> list[tuple[datetime, float]]:
    """Monta uma série ordenada a partir de {offset_em_minutos: incremento_mm}."""
    return sorted(
        (T0 + timedelta(minutes=off), val) for off, val in valores_por_offset.items()
    )


# --------------------------------------------------------------------------
# intensidade_na_janela
# --------------------------------------------------------------------------


def test_intensidade_e_media_sobre_o_tempo_observado() -> None:
    """3 leituras de 0,2 mm em 10 min cada => 0,6 mm em 30 min => 1,2 mm/h."""
    serie = _serie({-10: 0.2, 0: 0.2, 10: 0.2})
    mm_h, n, cobertura = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert n == 3
    assert cobertura == 30
    assert mm_h == pytest.approx(1.2)


def test_intensidade_usa_cobertura_real_nao_largura_da_janela() -> None:
    """Uma leitura só na janela cobre 10 min, não os 30 min nominais."""
    serie = _serie({0: 0.2})
    mm_h, n, cobertura = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert (n, cobertura) == (1, 10)
    assert mm_h == pytest.approx(1.2)


def test_janela_sem_leitura_devolve_none() -> None:
    serie = _serie({-60: 5.0, 60: 5.0})
    mm_h, n, cobertura = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert (mm_h, n, cobertura) == (None, 0, 0)


def test_janela_e_fechada_nos_dois_extremos() -> None:
    """Leituras exatamente em -15 e +15 min entram na janela."""
    serie = _serie({-15: 0.2, 15: 0.2})
    _, n, _ = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert n == 2


def test_leituras_zeradas_dao_intensidade_zero_nao_none() -> None:
    """Estação seca transmite 0.0; isso é informação, não ausência de dado."""
    serie = _serie({0: 0.0})
    mm_h, n, _ = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert n == 1 and mm_h == 0.0


# --------------------------------------------------------------------------
# classificar
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mm_h", "esperado"),
    [
        (0.0, "seco"),
        (1.2, "garoa"),
        (2.0, "garoa"),
        (3.5, "moderada"),
        (7.0, "moderada"),
        (12.0, "forte"),
        (37.8, "forte"),
    ],
)
def test_classificar_fora_da_zona_morta(mm_h: float, esperado: str) -> None:
    classe, motivo = rot.classificar(mm_h, 2.5, 10.0, 0.15)
    assert (classe, motivo) == (esperado, "")


@pytest.mark.parametrize("mm_h", [2.125, 2.5, 2.875, 8.5, 10.0, 11.5])
def test_classificar_na_zona_morta_exclui(mm_h: float) -> None:
    """±15% de 2,5 => [2.125, 2.875]; de 10 => [8.5, 11.5]."""
    classe, motivo = rot.classificar(mm_h, 2.5, 10.0, 0.15)
    assert classe == ""
    assert motivo == rot.MOTIVO_ZONA_MORTA


def test_zona_morta_zero_mantem_fronteiras_rotuladas() -> None:
    """Com zona morta desligada, o limiar pertence à classe de baixo.

    Intervalos do plano fechados à direita: garoa 0 < i <= 2,5 · moderada
    2,5 < i <= 10 · forte > 10.
    """
    assert rot.classificar(2.5, 2.5, 10.0, 0.0)[0] == "garoa"
    assert rot.classificar(2.5001, 2.5, 10.0, 0.0)[0] == "moderada"
    assert rot.classificar(10.0, 2.5, 10.0, 0.0)[0] == "moderada"
    assert rot.classificar(10.0001, 2.5, 10.0, 0.0)[0] == "forte"


# --------------------------------------------------------------------------
# rotular_frame
# --------------------------------------------------------------------------


def _estacoes_e_series(
    extras: dict[str, tuple[float, float, dict[int, float]]] | None = None,
) -> tuple[dict[str, rot.Estacao], dict[str, list[tuple[datetime, float]]]]:
    """Monta uma estação base 'E1' mais as extras pedidas."""
    estacoes = {"E1": rot.Estacao("E1", "Base", EST_LAT, EST_LON)}
    series = {"E1": _serie({-10: 0.2, 0: 0.2, 10: 0.2})}
    for eid, (lat, lon, vals) in (extras or {}).items():
        estacoes[eid] = rot.Estacao(eid, f"Est {eid}", lat, lon)
        series[eid] = _serie(vals)
    return estacoes, series


def _rotular(frame: rot.Frame, raio_km: float = 2.0, **kwargs) -> rot.LinhaManifest:
    estacoes, series = _estacoes_e_series(kwargs.pop("extras", None))
    return rot.rotular_frame(
        frame, estacoes, series, raio_km, 15, 10, 2.5, 10.0, 0.15, **kwargs
    )


def test_frame_sem_fix_sai_com_motivo_e_sem_classe() -> None:
    frame = rot.Frame("f.jpg", "p", T0, None, None)
    linha = _rotular(frame)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX
    assert linha.classe == "" and linha.mm_h is None


def test_frame_sem_timestamp_sai_com_motivo() -> None:
    frame = rot.Frame("f.jpg", "p", None, PERTO_LAT, PERTO_LON)
    linha = _rotular(frame)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_TIMESTAMP


def test_frame_fora_do_raio_sai_com_motivo() -> None:
    """Ponto a ~1,1 km da estação, com raio de 0,5 km."""
    frame = rot.Frame("f.jpg", "p", T0, -23.5400, EST_LON)
    linha = _rotular(frame, raio_km=0.5)
    assert linha.motivo_exclusao == rot.MOTIVO_FORA_DO_RAIO
    assert linha.n_estacoes_no_raio == 0


def test_frame_dentro_do_raio_e_rotulado_com_distancia_em_metros() -> None:
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = _rotular(frame)
    assert linha.classe == "garoa"
    assert linha.estacao_id == "E1"
    assert linha.mm_h == pytest.approx(1.2)
    assert linha.dist_m == pytest.approx(100.0, abs=5.0)


def test_estacao_no_raio_mas_sem_leitura_na_janela() -> None:
    frame = rot.Frame("f.jpg", "p", T0 + timedelta(hours=5), PERTO_LAT, PERTO_LON)
    linha = _rotular(frame)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_LEITURA
    assert linha.n_estacoes_no_raio == 1


def test_escolhe_a_estacao_mais_proxima_entre_candidatas() -> None:
    """E2 está mais longe e reporta chuva forte; deve perder para E1, mais perto."""
    extras = {"E2": (-23.5600, EST_LON, {0: 6.0})}
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = _rotular(frame, extras=extras)
    assert linha.estacao_id == "E1"
    assert linha.classe == "garoa"
    assert linha.n_estacoes_no_raio == 2


def test_cai_para_a_proxima_estacao_quando_a_mais_proxima_nao_tem_leitura() -> None:
    estacoes = {
        "E1": rot.Estacao("E1", "Perto sem dado", EST_LAT, EST_LON),
        "E2": rot.Estacao("E2", "Longe com dado", -23.5520, EST_LON),
    }
    series = {"E1": [], "E2": _serie({0: 0.2})}
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = rot.rotular_frame(frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15)
    assert linha.estacao_id == "E2"
    assert linha.classe == "garoa"


def test_desempate_entre_equidistantes_e_pelo_id() -> None:
    """Duas estações à mesma distância: ganha o menor id, para ser determinístico."""
    estacoes = {
        "E9": rot.Estacao("E9", "Nove", EST_LAT, EST_LON),
        "E1": rot.Estacao("E1", "Um", EST_LAT, EST_LON),
    }
    series = {"E9": _serie({0: 0.2}), "E1": _serie({0: 0.2})}
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = rot.rotular_frame(frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15)
    assert linha.estacao_id == "E1"


# --------------------------------------------------------------------------
# consenso regional (fallback quando não há estação com leitura no raio)
# --------------------------------------------------------------------------

# Estações a ~3,3 km do frame (0,03° de latitude), fora do raio de 2 km e
# dentro do raio de consenso de 5 km. A ~7,8 km fica uma que nunca entra.
_LONGE_LAT = EST_LAT - 0.03
_MUITO_LONGE_LAT = EST_LAT - 0.07
CONSENSO = rot.ConsensoRegional(raio_km=5.0, min_estacoes=3)


def _rotular_consenso(
    vals_por_estacao: dict[str, tuple[float, dict[int, float]]],
    consenso: rot.ConsensoRegional | None = CONSENSO,
) -> rot.LinhaManifest:
    estacoes = {
        eid: rot.Estacao(eid, f"Est {eid}", lat, EST_LON)
        for eid, (lat, _) in vals_por_estacao.items()
    }
    series = {eid: _serie(vals) for eid, (_, vals) in vals_por_estacao.items()}
    frame = rot.Frame("f.jpg", "p", T0, EST_LAT, EST_LON)
    return rot.rotular_frame(
        frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15, consenso=consenso
    )


def test_consenso_rotula_quando_todas_as_estacoes_concordam() -> None:
    linha = _rotular_consenso({
        "A": (_LONGE_LAT, {0: 0.2}),            # 1,2 mm/h
        "B": (_LONGE_LAT, {0: 0.1}),            # 0,6 mm/h
        "C": (_LONGE_LAT, {0: 0.2, 10: 0.2}),   # 1,2 mm/h
    })
    assert linha.classe == "garoa"
    assert linha.metodo_rotulo == rot.METODO_CONSENSO_REGIONAL
    assert linha.estacoes_consenso == "A;B;C"
    assert linha.mm_h == pytest.approx(1.2)      # mediana de 0,6 / 1,2 / 1,2
    assert linha.dist_m == pytest.approx(3336, abs=20)  # a mais longe usada
    assert linha.motivo_exclusao == ""


def test_consenso_seco_exige_todas_zeradas() -> None:
    zerada = {-10: 0.0, 0: 0.0, 10: 0.0}
    linha = _rotular_consenso({e: (_LONGE_LAT, zerada) for e in "ABC"})
    assert linha.classe == "seco"


def test_consenso_recusa_campo_heterogeneo() -> None:
    """Uma estação em moderada entre duas em garoa: classe no frame desconhecida."""
    linha = _rotular_consenso({
        "A": (_LONGE_LAT, {0: 0.2}),
        "B": (_LONGE_LAT, {0: 0.2}),
        "C": (_LONGE_LAT, {0: 1.0}),  # 6 mm/h
    })
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO
    assert linha.metodo_rotulo == ""


def test_consenso_recusa_se_alguma_estacao_cai_na_zona_morta() -> None:
    linha = _rotular_consenso({
        "A": (_LONGE_LAT, {0: 0.2}),
        "B": (_LONGE_LAT, {0: 0.2}),
        "C": (_LONGE_LAT, {0: 0.4}),  # 2,4 mm/h: zona morta de 2,5
    })
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO


def test_consenso_exige_minimo_de_estacoes_com_leitura() -> None:
    linha = _rotular_consenso({
        "A": (_LONGE_LAT, {0: 0.2}),
        "B": (_LONGE_LAT, {0: 0.2}),
        "C": (_LONGE_LAT, {}),               # sem leitura: não conta
        "D": (_MUITO_LONGE_LAT, {0: 0.2}),   # fora dos 5 km: não conta
    })
    assert linha.motivo_exclusao == rot.MOTIVO_POUCAS_ESTACOES
    assert linha.classe == ""


def test_consenso_ignora_discordancia_fora_do_raio_de_consenso() -> None:
    linha = _rotular_consenso({
        "A": (_LONGE_LAT, {0: 0.2}),
        "B": (_LONGE_LAT, {0: 0.2}),
        "C": (_LONGE_LAT, {0: 0.2}),
        "D": (_MUITO_LONGE_LAT, {0: 3.0}),  # forte, mas a 7,8 km
    })
    assert linha.classe == "garoa"
    assert linha.estacoes_consenso == "A;B;C"


def test_consenso_nao_substitui_estacao_proxima() -> None:
    """Com estação no raio de 2 km, o rótulo é dela mesmo que as distantes discordem."""
    linha = _rotular_consenso({
        "P": (PERTO_LAT, {0: 0.0}),
        "A": (_LONGE_LAT, {0: 0.2}),
        "B": (_LONGE_LAT, {0: 0.2}),
        "C": (_LONGE_LAT, {0: 0.2}),
    })
    assert linha.classe == "seco"
    assert linha.estacao_id == "P"
    assert linha.metodo_rotulo == rot.METODO_ESTACAO_PROXIMA


def test_sem_consenso_configurado_mantem_motivo_fora_do_raio() -> None:
    linha = _rotular_consenso(
        {e: (_LONGE_LAT, {0: 0.2}) for e in "ABC"}, consenso=None
    )
    assert linha.motivo_exclusao == rot.MOTIVO_FORA_DO_RAIO
    assert linha.classe == ""


# --------------------------------------------------------------------------
# confirmação regional do seco
# --------------------------------------------------------------------------


def _rotular_seco(
    vals_por_estacao: dict[str, tuple[float, dict[int, float]]],
    janela_seco_min: int | None = 60,
) -> rot.LinhaManifest:
    estacoes = {
        eid: rot.Estacao(eid, f"Est {eid}", lat, EST_LON)
        for eid, (lat, _) in vals_por_estacao.items()
    }
    series = {eid: _serie(vals) for eid, (_, vals) in vals_por_estacao.items()}
    frame = rot.Frame("f.jpg", "p", T0, EST_LAT, EST_LON)
    return rot.rotular_frame(
        frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15,
        consenso=CONSENSO, janela_seco_min=janela_seco_min,
    )


def test_seco_da_estacao_proxima_cai_se_vizinha_registra_chuva() -> None:
    """O caso de 01/09: estação perto lê zero, outra a ~3 km lê chuva na hora."""
    linha = _rotular_seco({
        "P": (PERTO_LAT, {0: 0.0}),
        "V": (_LONGE_LAT, {-10: 0.2}),
    })
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SECO_INCERTO
    assert linha.estacao_id == "P"  # auditável: qual estação leu o zero


def test_seco_cai_se_a_propria_estacao_choveu_na_janela_larga() -> None:
    """Zero na janela de ±15 min, mas báscula 40 min antes: garoa provável."""
    linha = _rotular_seco({"P": (PERTO_LAT, {-40: 0.2, 0: 0.0})})
    assert linha.motivo_exclusao == rot.MOTIVO_SECO_INCERTO


def test_seco_confirmado_quando_todas_as_estacoes_estao_zeradas() -> None:
    zerada = {-50: 0.0, 0: 0.0, 50: 0.0}
    linha = _rotular_seco({"P": (PERTO_LAT, zerada), "V": (_LONGE_LAT, zerada)})
    assert linha.classe == "seco"
    assert linha.metodo_rotulo == rot.METODO_ESTACAO_PROXIMA


def test_seco_ignora_chuva_fora_do_raio_e_fora_da_janela() -> None:
    linha = _rotular_seco({
        "P": (PERTO_LAT, {0: 0.0}),
        "L": (_MUITO_LONGE_LAT, {0: 2.0}),   # a 7,8 km
        "T": (_LONGE_LAT, {-90: 0.2}),        # fora de ±60 min
    })
    assert linha.classe == "seco"


def test_seco_por_consenso_tambem_exige_janela_larga() -> None:
    zero_curto = {0: 0.0}
    linha = _rotular_seco({
        "A": (_LONGE_LAT, zero_curto),
        "B": (_LONGE_LAT, zero_curto),
        "C": (_LONGE_LAT, {-30: 0.2, 0: 0.0}),
    })
    assert linha.motivo_exclusao == rot.MOTIVO_SECO_INCERTO


def test_sem_confirmacao_mantem_regra_antiga() -> None:
    linha = _rotular_seco(
        {"P": (PERTO_LAT, {0: 0.0}), "V": (_LONGE_LAT, {-10: 0.2})},
        janela_seco_min=None,
    )
    assert linha.classe == "seco"


def test_confirmacao_do_seco_nao_afeta_garoa() -> None:
    linha = _rotular_seco({
        "P": (PERTO_LAT, {0: 0.2}),
        "V": (_LONGE_LAT, {0: 0.0}),
    })
    assert linha.classe == "garoa"


def test_evento_id_combina_pasta_e_dia() -> None:
    frame = rot.Frame("f.jpg", "sessao_a", T0, PERTO_LAT, PERTO_LON)
    assert frame.evento_id == "sessao_a__2026-09-01"
    assert rot.Frame("f.jpg", "sessao_a", None, None, None).evento_id == (
        "sessao_a__sem_data"
    )


# --------------------------------------------------------------------------
# calcular_idade_posicao (J8 — idade da posição GPS)
# --------------------------------------------------------------------------


def test_idade_fix_atual_e_zero() -> None:
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": True}, fix=True, tem_posicao=True, ts=T0, ultimo_fix_observado=None
    )
    assert (idade, origem) == (0.0, rot.ORIGEM_FIX_ATUAL)


def test_idade_sem_posicao_e_vazia_mesmo_com_fix() -> None:
    """`tem_posicao=False` é o caso `gps.service` nunca teve fix — sem inferência possível."""
    idade, origem = rot.calcular_idade_posicao(
        gps={}, fix=False, tem_posicao=False, ts=T0, ultimo_fix_observado=T0
    )
    assert (idade, origem) == (None, "")


def test_idade_via_ultimo_fix_em_direto() -> None:
    """Schema 2: `ultimo_fix_em` grava o instante do último fix bom."""
    ultimo_fix_em = (T0 - timedelta(seconds=37)).isoformat().replace("+00:00", "Z")
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": False, "ultimo_fix_em": ultimo_fix_em},
        fix=False,
        tem_posicao=True,
        ts=T0,
        ultimo_fix_observado=None,
    )
    assert idade == pytest.approx(37.0)
    assert origem == rot.ORIGEM_ULTIMO_FIX_EM


def test_idade_ultimo_fix_em_invalido_cai_para_inferencia() -> None:
    """`ultimo_fix_em` corrompido ou posterior ao frame não pode ser usado."""
    ultimo_fix_observado = T0 - timedelta(seconds=10)
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": False, "ultimo_fix_em": "lixo-nao-parseavel"},
        fix=False,
        tem_posicao=True,
        ts=T0,
        ultimo_fix_observado=ultimo_fix_observado,
    )
    assert idade == pytest.approx(10.0)
    assert origem == rot.ORIGEM_INFERIDA_SEQUENCIA


def test_idade_ultimo_fix_em_no_futuro_e_descartado() -> None:
    """`ultimo_fix_em` posterior a `ts` é inconsistente — não confiar nele."""
    ultimo_fix_em_futuro = (T0 + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": False, "ultimo_fix_em": ultimo_fix_em_futuro},
        fix=False,
        tem_posicao=True,
        ts=T0,
        ultimo_fix_observado=None,
    )
    assert (idade, origem) == (None, "")


def test_idade_inferida_da_sequencia_schema1() -> None:
    """Schema 1 (sem `ultimo_fix_em`): idade vem do último fix observado na sessão."""
    ultimo_fix_observado = T0 - timedelta(seconds=22)
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": False},
        fix=False,
        tem_posicao=True,
        ts=T0,
        ultimo_fix_observado=ultimo_fix_observado,
    )
    assert idade == pytest.approx(22.0)
    assert origem == rot.ORIGEM_INFERIDA_SEQUENCIA


def test_idade_sem_historico_de_fix_na_sessao_e_vazia() -> None:
    """Sem `ultimo_fix_em` e sem fix anterior observado: não há como inferir."""
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": False}, fix=False, tem_posicao=True, ts=T0, ultimo_fix_observado=None
    )
    assert (idade, origem) == (None, "")


def test_idade_inferida_negativa_e_descartada() -> None:
    """Âncora posterior ao próprio frame é inconsistente (ordenação quebrada)."""
    ultimo_fix_observado = T0 + timedelta(seconds=5)
    idade, origem = rot.calcular_idade_posicao(
        gps={"fix": False},
        fix=False,
        tem_posicao=True,
        ts=T0,
        ultimo_fix_observado=ultimo_fix_observado,
    )
    assert (idade, origem) == (None, "")


# --------------------------------------------------------------------------
# rotular_frame com idade máxima da posição
# --------------------------------------------------------------------------


def test_frame_com_posicao_recente_sem_fix_e_rotulado_normalmente() -> None:
    """Fix caiu há pouco (idade pequena, inferida) — ainda dentro do raio da estação."""
    frame = rot.Frame(
        "f.jpg", "p", T0, PERTO_LAT, PERTO_LON,
        idade_posicao_s=5.0, origem_idade_posicao=rot.ORIGEM_INFERIDA_SEQUENCIA,
    )
    linha = _rotular(frame, idade_maxima_posicao_s=60.0)
    assert linha.classe == "garoa"
    assert linha.motivo_exclusao == ""
    assert linha.idade_posicao_s == pytest.approx(5.0)
    assert linha.origem_idade_posicao == rot.ORIGEM_INFERIDA_SEQUENCIA


def test_frame_com_posicao_desatualizada_e_excluido() -> None:
    """Idade conhecida, mas acima do limite configurado: motivo próprio e auditável."""
    frame = rot.Frame(
        "f.jpg", "p", T0, PERTO_LAT, PERTO_LON,
        idade_posicao_s=90.0, origem_idade_posicao=rot.ORIGEM_INFERIDA_SEQUENCIA,
    )
    linha = _rotular(frame, idade_maxima_posicao_s=60.0)
    assert linha.motivo_exclusao == rot.MOTIVO_POSICAO_DESATUALIZADA
    assert linha.classe == ""
    # A idade fica registrada mesmo excluído — é a rastreabilidade exigida pelo J8:
    # dá pra saber, olhando o manifest, que 90s > 60s foi o motivo exato.
    assert linha.idade_posicao_s == pytest.approx(90.0)


def test_frame_com_idade_desconhecida_e_tratado_como_sem_fix() -> None:
    """Posição presente mas sem nenhuma fonte de idade (sem histórico na sessão)."""
    frame = rot.Frame(
        "f.jpg", "p", T0, PERTO_LAT, PERTO_LON, idade_posicao_s=None, origem_idade_posicao=""
    )
    linha = _rotular(frame, idade_maxima_posicao_s=60.0)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX
    assert linha.classe == ""


def test_idade_maxima_padrao_de_rotular_frame_e_sem_limite() -> None:
    """Chamadas que não passam `idade_maxima_posicao_s` (código antigo) não regridem."""
    frame = rot.Frame(
        "f.jpg", "p", T0, PERTO_LAT, PERTO_LON,
        idade_posicao_s=10_000.0, origem_idade_posicao=rot.ORIGEM_INFERIDA_SEQUENCIA,
    )
    linha = rot.rotular_frame(
        frame, *_estacoes_e_series(), 2.0, 15, 10, 2.5, 10.0, 0.15
    )
    assert linha.classe == "garoa"


# --------------------------------------------------------------------------
# carregar_frames: inferência de idade a partir da própria sequência
# --------------------------------------------------------------------------


def _escrever_frame(
    pasta: Path, nome: str, ts: datetime, gps: dict[str, object]
) -> None:
    (pasta / f"{nome}.jpg").write_bytes(b"")
    (pasta / f"{nome}.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "capturado_em_utc": ts.isoformat(),
                "arquivo": f"{nome}.jpg",
                "gps": gps,
            }
        ),
        encoding="utf-8",
    )


def test_carregar_frames_infere_idade_da_sequencia_schema1(tmp_path: Path) -> None:
    """Um fix bom seguido de dois frames sem fix: idade cresce a partir do último fix real."""
    pasta = tmp_path / "sessao"
    pasta.mkdir()
    _escrever_frame(
        pasta, "frame_20260901_100000_000", T0,
        {"fix": True, "latitude": PERTO_LAT, "longitude": PERTO_LON},
    )
    _escrever_frame(
        pasta, "frame_20260901_100010_000", T0 + timedelta(seconds=10),
        {"fix": False, "latitude": PERTO_LAT, "longitude": PERTO_LON},
    )
    _escrever_frame(
        pasta, "frame_20260901_100025_000", T0 + timedelta(seconds=25),
        {"fix": False, "latitude": PERTO_LAT, "longitude": PERTO_LON},
    )
    frames, _ = rot.carregar_frames(tmp_path)
    por_arquivo = {f.arquivo: f for f in frames}

    fix_atual = por_arquivo["frame_20260901_100000_000.jpg"]
    assert fix_atual.idade_posicao_s == pytest.approx(0.0)
    assert fix_atual.origem_idade_posicao == rot.ORIGEM_FIX_ATUAL

    dez_s = por_arquivo["frame_20260901_100010_000.jpg"]
    assert dez_s.idade_posicao_s == pytest.approx(10.0)
    assert dez_s.origem_idade_posicao == rot.ORIGEM_INFERIDA_SEQUENCIA

    # Conservador por construção: a âncora é o ÚLTIMO FIX REAL observado
    # (frame de 10:00:00), não o frame anterior na sequência (que já estava
    # sem fix) — a idade cresce a partir da mesma âncora, nunca reinicia.
    vinte_cinco_s = por_arquivo["frame_20260901_100025_000.jpg"]
    assert vinte_cinco_s.idade_posicao_s == pytest.approx(25.0)
    assert vinte_cinco_s.origem_idade_posicao == rot.ORIGEM_INFERIDA_SEQUENCIA


def test_carregar_frames_nao_atravessa_fronteira_de_dia_na_mesma_pasta(
    tmp_path: Path,
) -> None:
    """Duas sessões (dias diferentes) na mesma pasta não compartilham âncora de fix."""
    pasta = tmp_path / "sessao_mista"
    pasta.mkdir()
    dia1 = datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)
    dia2 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    _escrever_frame(
        pasta, "frame_20260807_100000_000", dia1,
        {"fix": True, "latitude": PERTO_LAT, "longitude": PERTO_LON},
    )
    # Primeiro frame do dia seguinte já chega sem fix: não pode herdar a âncora do dia1.
    _escrever_frame(
        pasta, "frame_20260901_100000_000", dia2,
        {"fix": False, "latitude": PERTO_LAT, "longitude": PERTO_LON},
    )
    frames, _ = rot.carregar_frames(tmp_path)
    por_arquivo = {f.arquivo: f for f in frames}

    primeiro_do_dia2 = por_arquivo["frame_20260901_100000_000.jpg"]
    assert primeiro_do_dia2.idade_posicao_s is None
    assert primeiro_do_dia2.origem_idade_posicao == ""


def test_carregar_frames_le_ultimo_fix_em_schema2(tmp_path: Path) -> None:
    """Schema 2: `gps.ultimo_fix_em` tem prioridade sobre a inferência por sequência."""
    pasta = tmp_path / "sessao_schema2"
    pasta.mkdir()
    ultimo_fix_em = (T0 - timedelta(seconds=8)).isoformat().replace("+00:00", "Z")
    _escrever_frame(
        pasta, "frame_20260901_100000_000", T0,
        {"fix": False, "latitude": PERTO_LAT, "longitude": PERTO_LON,
         "ultimo_fix_em": ultimo_fix_em},
    )
    frames, _ = rot.carregar_frames(tmp_path)
    assert len(frames) == 1
    assert frames[0].idade_posicao_s == pytest.approx(8.0)
    assert frames[0].origem_idade_posicao == rot.ORIGEM_ULTIMO_FIX_EM


def test_carregar_frames_lat_lon_nulos_sem_fix_fica_sem_idade(tmp_path: Path) -> None:
    """`gps.service` nunca teve fix: sem posição, sem idade, sem inferência possível."""
    pasta = tmp_path / "sessao_sem_fix"
    pasta.mkdir()
    _escrever_frame(
        pasta, "frame_20260901_100000_000", T0,
        {"fix": False, "latitude": None, "longitude": None},
    )
    frames, _ = rot.carregar_frames(tmp_path)
    assert frames[0].lat is None and frames[0].lon is None
    assert frames[0].idade_posicao_s is None
    assert frames[0].origem_idade_posicao == ""


# --------------------------------------------------------------------------
# parsing de timestamp
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "2026-09-01T10:00:00Z",
        "2026-09-01T10:00:00+00:00",
        "2026-09-01T07:00:00-03:00",
        "2026-09-01T10:00:00",
    ],
)
def test_parse_ts_normaliza_para_utc(texto: str) -> None:
    assert rot._parse_ts(texto) == T0


@pytest.mark.parametrize("texto", ["", "nao-e-data", "2026-13-45T99:99:99Z"])
def test_parse_ts_invalido_devolve_none(texto: str) -> None:
    assert rot._parse_ts(texto) is None


# --------------------------------------------------------------------------
# ponta a ponta: main() sobre uma árvore sintética
# --------------------------------------------------------------------------


def _montar_arvore(tmp_path: Path) -> Path:
    """Cria frames, CSV de leituras e config; devolve o caminho do config."""
    raiz = tmp_path / "processed"
    pasta = raiz / "sessao_teste"
    pasta.mkdir(parents=True)

    # Dois frames com fix perto da estação, um sem fix.
    frames = [
        ("frame_a", PERTO_LAT, PERTO_LON, True),
        ("frame_b", PERTO_LAT, PERTO_LON, True),
        ("frame_c", None, None, False),
    ]
    for nome, lat, lon, fix in frames:
        (pasta / f"{nome}.jpg").write_bytes(b"")
        (pasta / f"{nome}.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "capturado_em_utc": T0.isoformat(),
                    "arquivo": f"{nome}.jpg",
                    "gps": {
                        "fix": fix,
                        "latitude": lat,
                        "longitude": lon,
                    },
                }
            ),
            encoding="utf-8",
        )
    # Arquivo auxiliar que não é frame: não deve virar linha do manifest.
    (pasta / "_normalizacao.json").write_text("{}", encoding="utf-8")
    # Jpg sem json par: contado no relatório, fora do manifest.
    (pasta / "frame_orfao.jpg").write_bytes(b"")

    leituras = tmp_path / "leituras.csv"
    with leituras.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["fonte", "estacao_id", "estacao_nome", "lat", "lon", "ts_utc",
             "acumulado_mm", "janela_min"]
        )
        for off in (-10, 0, 10):
            ts = (T0 + timedelta(minutes=off)).isoformat().replace("+00:00", "Z")
            w.writerow(["teste", "E1", "Base", EST_LAT, EST_LON, ts, 0.2, 10])

    config = {
        "raiz_frames": str(raiz),
        "leituras_csv": str(leituras),
        "saida_manifest": str(tmp_path / "out" / "manifest.csv"),
        "saida_relatorio": str(tmp_path / "out" / "relatorio.json"),
        "leitura": {"minutos_por_leitura": 10},
        "rotulagem": {
            "raio_max_km": 2.0,
            "janela_min": 15,
            "zona_morta_frac": 0.15,
            "idade_maxima_posicao_s": 60.0,
            "limiares_mm_h": {"garoa_max": 2.5, "moderada_max": 10.0},
        },
        "sensibilidade_raio_km": [2.0],
        "sensibilidade_idade_maxima_s": [60.0],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_main_escreve_manifest_com_todas_as_colunas(tmp_path: Path) -> None:
    config_path = _montar_arvore(tmp_path)
    assert rot.main(["--config", str(config_path)]) == 0

    manifest = tmp_path / "out" / "manifest.csv"
    with manifest.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))

    assert list(linhas[0].keys()) == list(rot.COLUNAS_MANIFEST)
    # 3 frames com json; o _normalizacao.json e o jpg órfão ficam fora.
    assert len(linhas) == 3
    por_arquivo = {li["arquivo"]: li for li in linhas}
    assert por_arquivo["frame_a.jpg"]["classe"] == "garoa"
    assert por_arquivo["frame_a.jpg"]["mm_h"] == "1.2000"
    assert por_arquivo["frame_a.jpg"]["motivo_exclusao"] == ""
    # frame_a tem fix atual no fixture (_montar_arvore): idade 0, origem fix_atual.
    assert por_arquivo["frame_a.jpg"]["idade_posicao_s"] == "0.0"
    assert por_arquivo["frame_a.jpg"]["origem_idade_posicao"] == rot.ORIGEM_FIX_ATUAL
    assert por_arquivo["frame_c.jpg"]["classe"] == ""
    assert por_arquivo["frame_c.jpg"]["motivo_exclusao"] == rot.MOTIVO_SEM_FIX
    assert por_arquivo["frame_c.jpg"]["idade_posicao_s"] == ""
    assert por_arquivo["frame_c.jpg"]["origem_idade_posicao"] == ""

    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["rotulados"] == 2
    assert relatorio["por_classe"]["garoa"] == 2
    assert relatorio["por_motivo"][rot.MOTIVO_SEM_FIX] == 1
    assert relatorio["total_jpg_sem_json"] == 1
    assert relatorio["config_sha256"]
    assert relatorio["parametros"]["raio_max_km"] == 2.0
    assert relatorio["parametros"]["idade_maxima_posicao_s"] == 60.0
    assert relatorio["por_origem_idade_posicao"][rot.ORIGEM_FIX_ATUAL] == 2


def test_main_e_reproduzivel_byte_a_byte(tmp_path: Path) -> None:
    """Mesmo input ⇒ mesmo manifest, exigência de aceite de F1.3."""
    config_path = _montar_arvore(tmp_path)
    manifest = tmp_path / "out" / "manifest.csv"

    rot.main(["--config", str(config_path)])
    primeiro = manifest.read_bytes()
    rot.main(["--config", str(config_path)])
    assert manifest.read_bytes() == primeiro


def test_dry_run_nao_escreve_nada(tmp_path: Path) -> None:
    config_path = _montar_arvore(tmp_path)
    assert rot.main(["--config", str(config_path), "--dry-run"]) == 0
    assert not (tmp_path / "out").exists()


def test_raio_km_da_cli_sobrescreve_o_config(tmp_path: Path) -> None:
    config_path = _montar_arvore(tmp_path)
    assert rot.main(["--config", str(config_path), "--raio-km", "0.01"]) == 0
    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["parametros"]["raio_max_km"] == 0.01
    assert relatorio["rotulados"] == 0
    assert relatorio["por_motivo"][rot.MOTIVO_FORA_DO_RAIO] == 2


def test_idade_maxima_posicao_s_da_cli_sobrescreve_o_config(tmp_path: Path) -> None:
    """frame_a e frame_b têm fix atual (idade 0): mesmo um limite de 0s não os exclui."""
    config_path = _montar_arvore(tmp_path)
    assert rot.main(
        ["--config", str(config_path), "--idade-maxima-posicao-s", "0"]
    ) == 0
    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["parametros"]["idade_maxima_posicao_s"] == 0.0
    assert relatorio["rotulados"] == 2


# --------------------------------------------------------------------------
# D2: zona morta do consenso regional aplicada à mediana
# --------------------------------------------------------------------------

CONSENSO_MEDIANA = rot.ConsensoRegional(
    raio_km=5.0, min_estacoes=3, zona_morta_na_mediana=True
)


def _consenso_mediana(incrementos: list[float]) -> rot.LinhaManifest:
    """Três estações com um único incremento (x6 = mm/h) cada."""
    return _rotular_consenso(
        {
            eid: (_LONGE_LAT, {0: inc})
            for eid, inc in zip("ABC", incrementos)
        },
        consenso=CONSENSO_MEDIANA,
    )


def test_mediana_resgata_estacao_isolada_na_zona_morta() -> None:
    """{1,2; 1,2; 2,4}: mediana 1,2 fora da zona morta => garoa."""
    linha = _consenso_mediana([0.2, 0.2, 0.4])
    assert linha.classe == "garoa"
    assert linha.metodo_rotulo == rot.METODO_CONSENSO_REGIONAL
    assert linha.mm_h == pytest.approx(1.2)


def test_mediana_recusa_classes_diferentes() -> None:
    """{2,4; 2,4; 2,6}: 2,6 é moderada sem zona morta => classes diferentes."""
    linha = _consenso_mediana([0.4, 0.4, 0.43333333])
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO


def test_mediana_recusa_se_a_propria_mediana_cai_na_zona_morta() -> None:
    """{2,3; 2,4; 2,4}: todas garoa, mas a mediana 2,4 está na zona morta."""
    linha = _consenso_mediana([0.38333333, 0.4, 0.4])
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO


def test_regra_antiga_continua_recusando_o_caso_resgatado() -> None:
    """Com `zona_morta_na_mediana=False` (default) {1,2; 1,2; 2,4} segue excluído."""
    linha = _rotular_consenso({
        "A": (_LONGE_LAT, {0: 0.2}),
        "B": (_LONGE_LAT, {0: 0.2}),
        "C": (_LONGE_LAT, {0: 0.4}),
    })
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO


# --------------------------------------------------------------------------
# D1: seco sem GPS por consenso metropolitano + coluna `periodo`
# --------------------------------------------------------------------------

METRO = rot.ConsensoMetropolitano(min_estacoes=5, janela_min=60)
_ZERADA = {-10: 0.0, 0: 0.0, 10: 0.0}


def _rotular_sem_gps(
    series_por_estacao: dict[str, dict[int, float]],
    metro: rot.ConsensoMetropolitano | None = METRO,
    lat: float | None = None,
    lon: float | None = None,
) -> rot.LinhaManifest:
    estacoes = {
        eid: rot.Estacao(eid, f"Est {eid}", EST_LAT - 0.01 * i, EST_LON)
        for i, eid in enumerate(series_por_estacao)
    }
    series = {eid: _serie(v) for eid, v in series_por_estacao.items()}
    frame = rot.Frame("f.jpg", "p", T0, lat, lon)
    return rot.rotular_frame(
        frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15, metropolitano=metro
    )


def test_metropolitano_todas_zeradas_rotula_seco() -> None:
    linha = _rotular_sem_gps({e: _ZERADA for e in "ABCDE"})
    assert linha.classe == "seco"
    assert linha.metodo_rotulo == rot.METODO_CONSENSO_METROPOLITANO
    assert linha.estacoes_consenso == "A;B;C;D;E"
    assert linha.motivo_exclusao == ""
    assert linha.mm_h == 0.0


def test_metropolitano_uma_estacao_com_chuva_exclui() -> None:
    series = {e: _ZERADA for e in "ABCDE"}
    series["C"] = {-10: 0.0, 0: 0.2, 10: 0.0}
    linha = _rotular_sem_gps(series)
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX


def test_metropolitano_chuva_na_borda_da_janela_larga_exclui() -> None:
    """A janela é de ±60 min, bem maior que os ±15 min da estação próxima."""
    series = {e: _ZERADA for e in "ABCDE"}
    series["A"] = {0: 0.0, 55: 0.2}
    assert _rotular_sem_gps(series).classe == ""


def test_metropolitano_menos_de_cinco_estacoes_exclui() -> None:
    linha = _rotular_sem_gps({e: _ZERADA for e in "ABCD"})
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX


def test_metropolitano_estacao_sem_leitura_na_janela_nao_conta() -> None:
    series = {e: _ZERADA for e in "ABCD"}
    series["E"] = {}
    assert _rotular_sem_gps(series).classe == ""


def test_metropolitano_nunca_rotula_garoa_sem_gps() -> None:
    linha = _rotular_sem_gps({e: {0: 0.2} for e in "ABCDE"})
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX


def test_metropolitano_desligado_mantem_sem_gps_fix() -> None:
    linha = _rotular_sem_gps({e: _ZERADA for e in "ABCDE"}, metro=None)
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX


def test_metropolitano_nunca_se_aplica_a_frame_com_gps() -> None:
    """Frame com posição segue as regras de estação (aqui: nenhuma no raio de 2 km)."""
    series = {e: _ZERADA for e in "ABCDE"}
    linha = _rotular_sem_gps(series, lat=EST_LAT - 0.2, lon=EST_LON)
    assert linha.metodo_rotulo != rot.METODO_CONSENSO_METROPOLITANO
    assert linha.classe == ""
    assert linha.motivo_exclusao == rot.MOTIVO_FORA_DO_RAIO


def test_metropolitano_sem_timestamp_nao_rotula() -> None:
    frame = rot.Frame("f.jpg", "p", None, None, None)
    linha = rot.rotular_frame(
        frame, {}, {}, 2.0, 15, 10, 2.5, 10.0, 0.15, metropolitano=METRO
    )
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_TIMESTAMP
    assert linha.periodo == ""


@pytest.mark.parametrize(
    ("utc", "esperado"),
    [
        ((2026, 9, 1, 9, 0), "dia"),      # 06:00 local: início do dia
        ((2026, 9, 1, 8, 59), "noite"),   # 05:59 local
        ((2026, 9, 1, 21, 29), "dia"),    # 18:29 local
        ((2026, 9, 1, 21, 30), "noite"),  # 18:30 local: início da noite
        ((2026, 8, 7, 1, 31), "noite"),   # 22:31 local de 06/08
    ],
)
def test_periodo_do_dia_pelo_horario_local(
    utc: tuple[int, int, int, int, int], esperado: str
) -> None:
    assert rot.periodo_do_dia(datetime(*utc, tzinfo=timezone.utc)) == esperado


def test_periodo_do_dia_sem_timestamp_e_vazio() -> None:
    assert rot.periodo_do_dia(None) == ""


def test_main_flags_novas_ligam_e_desligam_as_regras(tmp_path: Path) -> None:
    """Com as regras ligadas no config e depois desligadas por CLI, o manifest
    desligado é o prefixo exato do ligado nas linhas rotuladas pela regra antiga."""
    config_path = _montar_arvore(tmp_path)
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cfg["rotulagem"]["consenso_metropolitano"] = {
        "ativo": True, "min_estacoes": 1, "janela_min": 60,
    }
    cfg["rotulagem"]["consenso_regional"] = {
        "ativo": True, "raio_km": 5.0, "min_estacoes": 3,
        "zona_morta_na_mediana": True,
    }
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    manifest = tmp_path / "out" / "manifest.csv"

    # Série de _montar_arvore tem 0,2 mm/h: chuva => frame_c continua sem GPS fix.
    assert rot.main(["--config", str(config_path)]) == 0
    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["parametros"]["consenso_metropolitano_min_estacoes"] == 1
    assert relatorio["parametros"]["consenso_zona_morta_na_mediana"] is True
    por_arquivo = {
        li["arquivo"]: li
        for li in csv.DictReader(manifest.open(encoding="utf-8", newline=""))
    }
    assert por_arquivo["frame_c.jpg"]["motivo_exclusao"] == rot.MOTIVO_SEM_FIX
    assert por_arquivo["frame_c.jpg"]["periodo"] == "dia"

    assert rot.main([
        "--config", str(config_path),
        "--sem-consenso-metropolitano", "--sem-zona-morta-mediana",
    ]) == 0
    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["parametros"]["consenso_metropolitano_min_estacoes"] is None
    assert relatorio["parametros"]["consenso_zona_morta_na_mediana"] is False


# --------------------------------------------------------------------------
# zero de báscula: estação zerada com chuva recente não vota no consenso
# --------------------------------------------------------------------------

_CONSENSO_BASCULA = rot.ConsensoRegional(
    raio_km=5.0, min_estacoes=3, zona_morta_na_mediana=True,
    zero_de_bascula_neutro=True,
)


def _rotular_bascula(
    vals_por_estacao: dict[str, dict[int, float]],
    consenso: rot.ConsensoRegional = _CONSENSO_BASCULA,
) -> rot.LinhaManifest:
    estacoes = {
        eid: rot.Estacao(eid, f"Est {eid}", _LONGE_LAT, EST_LON)
        for eid in vals_por_estacao
    }
    series = {eid: _serie(v) for eid, v in vals_por_estacao.items()}
    frame = rot.Frame("f.jpg", "p", T0, EST_LAT, EST_LON)
    return rot.rotular_frame(
        frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15,
        consenso=consenso, janela_seco_min=60,
    )


def test_zero_com_chuva_recente_fica_neutro_e_consenso_da_garoa() -> None:
    """O caso de 01/09: [0,0; 1,2; 1,2] com a zerada tendo tombado 30 min antes."""
    linha = _rotular_bascula({
        "A": {0: 0.2},
        "B": {0: 0.2},
        "Z": {-30: 0.2, 0: 0.0},
    })
    assert linha.classe == "garoa"
    assert linha.estacoes_consenso == "A;B;neutras:Z"
    assert linha.mm_h == pytest.approx(1.2)


def test_zero_sem_chuva_recente_continua_derrubando_o_consenso() -> None:
    linha = _rotular_bascula({"A": {0: 0.2}, "B": {0: 0.2}, "Z": {0: 0.0}})
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO


def test_zero_ao_lado_de_moderada_nao_fica_neutro() -> None:
    linha = _rotular_bascula({
        "A": {0: 1.0},  # 6 mm/h
        "B": {0: 1.0},
        "Z": {-30: 0.2, 0: 0.0},
    })
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO


def test_zero_neutro_exige_duas_votantes() -> None:
    linha = _rotular_bascula({
        "A": {0: 0.2},
        "Y": {-30: 0.2, 0: 0.0},
        "Z": {-30: 0.2, 0: 0.0},
    })
    assert linha.classe == ""


def test_flag_desligada_mantem_zero_votando() -> None:
    linha = _rotular_bascula(
        {"A": {0: 0.2}, "B": {0: 0.2}, "Z": {-30: 0.2, 0: 0.0}},
        consenso=rot.ConsensoRegional(5.0, 3, True, False),
    )
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_CONSENSO
