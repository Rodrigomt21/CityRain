"""Gerador sintético de chuva calibrada (spec D7, dataset balanceado de intensidade).

O gerador recebe um frame REAL de garoa (a base) e ACRESCENTA chuva até um
``mm_h_alvo`` (moderada ou forte). Ele nunca parte de um frame seco: o chão
molhado, o céu fechado e o limpador já fazem parte da base, então nenhum deles
vira atalho para o classificador (ver spec, "O que as outras fotos ensinam").

Camadas, aplicadas nesta ordem (cada uma pode ser desligada na config):

1. **Névoa** (``nevoa``): modelo de Koschmieder ``I = J·t + A·(1−t)`` com
   ``t = exp(−β·d)``. A profundidade ``d`` vem da posição vertical relativa ao
   horizonte (plano do chão visto por câmera pinhole: ``d ∝ 1/(y−y_h)``,
   saturando em ``d_max``; tudo acima do horizonte vale ``d_max``). Só entra o
   *incremento* de extinção ``β(mm_h_alvo) − β(mm_h_base)``, porque a base já
   carrega a névoa da própria garoa.
2. **Riscos** (``streaks``): traços finos, curtos e fracos (a 1 fps e de dia
   quase não se veem; Garg & Nayar 2006; Halder et al. 2019). Densidade
   proporcional ao mm/h, opacidade com teto baixo para não virar "neblina de
   riscos".
3. **Película d'água** (``pelicula``): regiões de desfoque e distorção suave do
   vidro, com área proporcional ao mm/h (saturando).
4. **Gotas no vidro** (``gotas``): densidade proporcional a
   ``mm_h_alvo/mm_h_base`` com TETO de saturação (``teto_saturacao``), que
   modela o limpador: em chuva forte o limpador está ligado e a contagem de
   gotas não cresce sem limite. Aparência por refração (patch do entorno
   invertido verticalmente e desfocado dentro da gota) mais borda escura e um
   pequeno brilho especular. O FORMATO principal são elipses
   irregulares anti-aliased; as máscaras do RaindropsOnWindshield entram só
   como minoria (<= 20%, arredondadas), reduzidas à escala das NOSSAS gotas
   (pequenas, numerosas, quase em foco): o dataset público fornece forma, não
   escala.
5. **Spray** (``spray``): desligado no v1 (não implementado; chave reservada).

Todas as camadas respeitam uma máscara de proteção que preserva a faixa
inferior do quadro (capô/painel, ``d ≈ 0``): ali não há névoa nem gotas
sintéticas.

Relação empírica de extinção por chuva (fonte da névoa)
-------------------------------------------------------
``β(R) = γ · R^ε`` [km⁻¹], com R em mm/h. Usa-se a forma potência clássica da
extinção óptica por chuva no visível, atribuída a Chu & Hogg (1968), "Effects of
precipitation on propagation at 0.63, 3.5 and 10.6 microns", Bell System
Technical Journal 47(5), com ``γ = 1,076`` e ``ε = 0,67`` (valores como citados
em revisões de visibilidade em chuva, p. ex. Kanazawa & Uchida, HESS 2025, e
Roser et al. 2009 para o uso em visão veicular).

ATENÇÃO — PROVISÓRIO: as constantes foram transcritas de memória, não
conferidas contra o artigo original, e a literatura varia bastante conforme o
comprimento de onda e a distribuição de gotas. Por isso ``γ``, ``ε`` e a
distância ``d_max`` ficam em ``sintetico_v1.yaml`` (seção ``calibracao``), marcadas como
provisórias; o ajuste final deve vir da régua do D6 (contraste ao longe em
23/09 e nos vídeos YouTube).

Determinismo: toda aleatoriedade sai de ``numpy.random.default_rng(seed)``.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from scipy import ndimage as ndi

__all__ = [
    "CAMADAS",
    "ResultadoSintetico",
    "beta_extincao",
    "carregar_banco_formas",
    "config_padrao",
    "gerar_amostra",
    "hash_imagem",
    "sortear_mm_h_alvo",
]

CAMADAS: tuple[str, ...] = ("nevoa", "streaks", "pelicula", "gotas", "spray")

# Banco de formas de gota é caro de montar (milhares de PNG 1280x1024); fica em
# cache de processo, indexado pelo diretório e pelo número de formas.
_CACHE_BANCO: dict[tuple[str, int], list[np.ndarray]] = {}


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
def config_padrao() -> dict[str, Any]:
    """Devolve a configuração padrão (espelho de ``sintetico_v1.yaml``).

    Existe para que o módulo e os testes funcionem sem depender do arquivo
    YAML; o YAML sobrescreve estes valores via :func:`_mesclar`.

    Returns:
        Dicionário aninhado com ``geometria``, ``calibracao`` e ``camadas``.
    """
    return {
        "geometria": {
            "horizonte_y": 0.56,  # fração da altura onde fica o horizonte
            "capo_y": 0.80,  # fração da altura onde começa o capô/painel
            "capo_suavizacao": 0.035,  # largura da transição (fração da altura)
            "largura_ref": 640,  # escala em que os tamanhos em px são definidos
        },
        "calibracao": {
            "provisorio": True,
            "beta_gamma_km": 1.076,  # Chu & Hogg (1968), provisório
            "beta_epsilon": 0.67,  # idem
            "d_max_m": 120.0,  # distância efetiva do horizonte, provisório
            "d_camera_m": 5.0,  # profundidade ao nível do capô
            "perfil_expoente": 1.3,  # curvatura do perfil d(y) entre capô e horizonte
            "densidade_gotas_base_mpx": 290.0,  # gotas/Mpx na base a mm_h_base
            "luz_ar_fator": 0.85,  # A = média do céu da base x fator (<1: sem atalho de brilho)
            "escurecimento_max": 0.08,  # escurecimento global em 40 mm/h (chuva real é mais escura)
        },
        "forte": {
            # rampa 0 (moderada) -> 1 (forte) entre mm_ini e mm_fim: tudo que é
            # exclusivo do forte é multiplicado por ela, então a moderada não muda
            "mm_ini": 8.5,
            "mm_fim": 12.0,
            "beta_extra": 0.15,  # +25% de extinção
            "dessaturacao": 0.25,
            "escurecimento_extra": 0.04,
            "pelicula_area_extra": 0.05,
            "pelicula_desfoque_extra": -0.4,
            "pelicula_distorcao_extra": 0.0,  # px a mais de distorção da película (v2)
            # véu: perda de contraste global, inclusive perto da câmera (água espalhada
            # no vidro + spray). A névoa por profundidade não cobre o primeiro plano. 0 = v1.
            "veu": 0.0,
            "gotas_grandes_mpx": 340.0,  # gotas grandes/borradas por Mpx (a 1.0)
            "raio_grande_mediana_px": 5.5,
            "raio_grande_sigma": 0.35,
            "raio_grande_min_px": 3.5,
            "raio_grande_max_px": 11.0,
            "desfoque_grande_px": 0.9,
            "coalescencia_frac": 0.3,
            "escorridos_frac": 0.35,
            "escorrido_comprimento_px": [14.0, 42.0],
        },
        "camadas": {
            "nevoa": {"ativa": True, "escala_beta": 0.30},
            "streaks": {
                "ativa": True,
                "por_mm_h": 14.0,
                "max_streaks": 450,
                "comprimento_px": [10.0, 26.0],
                "angulo_graus": 6.0,
                "opacidade_max": 0.09,
            },
            "pelicula": {
                "ativa": True,
                "area_por_mm_h": 0.04,
                "area_max": 0.3,
                "escala_px": 70.0,
                "desfoque_px": 0.8,
                "distorcao_px": 1.8,
                "distorcao_escala_px": 26.0,
            },
            "gotas": {
                "ativa": True,
                "teto_saturacao": 1.3,
                "raio_mediana_px": 3.4,
                "raio_sigma": 0.5,
                "raio_max_px": 13.0,
                "cauda_grande_por_mm_h": 0.002,
                "formas_dir": "ml/data/raw/public_datasets/raindrops_zenodo/masks",
                "n_formas": 300,
                "passo_arquivos": 6,
                "borda_escura": 0.5,
                "brilho": 0.15,
                "agrupamento": 0.6,
                "desfoque_gota_px": 0.9,
                "escurecimento_gota": -0.12,
                "varredura_reducao": 0.7,
            },
            "spray": {"ativa": False},
        },
    }


def _mesclar(base: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    """Mescla recursivamente ``extra`` sobre ``base`` sem alterar nenhum dos dois."""
    saida = copy.deepcopy(base)
    for chave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = _mesclar(saida[chave], valor)
        else:
            saida[chave] = copy.deepcopy(valor)
    return saida


# --------------------------------------------------------------------------- #
# Utilidades públicas
# --------------------------------------------------------------------------- #
def beta_extincao(mm_h: float, gamma_km: float = 1.076, epsilon: float = 0.67) -> float:
    """Coeficiente de extinção por chuva ``β = γ·R^ε`` em km⁻¹ (Chu & Hogg, 1968).

    Constantes provisórias (ver docstring do módulo).

    Args:
        mm_h: Taxa de chuva em mm/h (>= 0).
        gamma_km: Fator multiplicativo da lei de potência.
        epsilon: Expoente da lei de potência.

    Returns:
        Extinção em km⁻¹.
    """
    return float(gamma_km * max(mm_h, 0.0) ** epsilon)


def sortear_mm_h_alvo(
    classe: str, rng: np.random.Generator, faixas: dict[str, Sequence[float]]
) -> float:
    """Sorteia ``mm_h_alvo`` uniforme na faixa da classe (fora das zonas mortas).

    Args:
        classe: ``"moderada"`` ou ``"forte"``.
        rng: Gerador aleatório já semeado.
        faixas: Mapa classe -> ``[mínimo, máximo]`` em mm/h.

    Returns:
        Taxa alvo em mm/h, arredondada a 2 casas.
    """
    lo, hi = faixas[classe]
    return round(float(rng.uniform(lo, hi)), 2)


def hash_imagem(imagem: np.ndarray) -> str:
    """SHA-256 dos bytes da imagem, usado para provar determinismo por seed."""
    return hashlib.sha256(np.ascontiguousarray(imagem).tobytes()).hexdigest()


@dataclass
class ResultadoSintetico:
    """Saída de :func:`gerar_amostra`.

    Attributes:
        imagem: Imagem BGR uint8 gerada.
        parametros: Parâmetros efetivos de cada camada (vão para o manifest).
    """

    imagem: np.ndarray
    parametros: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Banco de formas de gota
# --------------------------------------------------------------------------- #
def _formas_elipticas(n: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Elipses levemente irregulares, anti-aliased: o formato PRINCIPAL das gotas.

    Por que: gota no vidro é arredondada com contorno suave. O raio varia com
    ruído de baixa frequência (harmônicos 2 a 4) e o eixo vertical é um pouco
    maior (gotas escorrem). Rasteriza-se a 4x e reduz-se com média de área para
    ter borda anti-aliased (sem recorte duro), com margem de 4 px de alfa zero.
    """
    formas = []
    for _ in range(n):
        lado, ss = 64, 4
        ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        raio = np.ones_like(ang)
        for k, amp in ((2, 0.10), (3, 0.06), (4, 0.04)):
            raio += rng.uniform(-amp, amp) * np.cos(k * ang + rng.uniform(0, 2 * np.pi))
        asp = rng.uniform(0.62, 1.0)  # largura / altura
        r0 = (lado / 2 - 5) * ss
        pts = np.stack(
            [lado * ss / 2 + r0 * asp * raio * np.cos(ang), lado * ss / 2 + r0 * raio * np.sin(ang)], axis=1
        )
        m = np.zeros((lado * ss, lado * ss), np.float32)
        cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 1.0, cv2.LINE_AA)
        m = cv2.resize(m, (lado, lado), interpolation=cv2.INTER_AREA)
        m = cv2.GaussianBlur(m, (0, 0), 0.9)
        ys, xs = np.nonzero(m > 0.01)
        formas.append(np.pad(m[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], 1))
    return formas


def _arredondar_mascara(comp: np.ndarray) -> np.ndarray:
    """Fecha, borra forte e re-binariza suavemente um componente de máscara.

    Por que: os componentes crus do RaindropsOnWindshield são poligonais/
    retangulares e, reduzidos, viram "flocos" ou retângulos de borda dura.
    Fechamento + blur forte + limiar suave arredondam o contorno e dão borda
    anti-aliased; margem de 4 px garante alfa zero na borda do recorte.
    """
    m = np.pad(comp.astype(np.float32), 5)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    m = cv2.GaussianBlur(m, (0, 0), 3.0)
    m = np.clip((m - 0.5) * 3.0 + 0.5, 0.0, 1.0)
    m = cv2.GaussianBlur(m, (0, 0), 0.9)
    ys, xs = np.nonzero(m > 0.01)
    if ys.size == 0:
        return m
    return np.pad(m[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], 1)


def carregar_banco_formas(
    formas_dir: str | Path | None,
    n_formas: int = 300,
    passo_arquivos: int = 6,
    frac_mascaras: float = 0.2,
) -> list[np.ndarray]:
    """Monta o banco de formas de gota (maioria elipses, minoria máscaras reais).

    Por que: o dataset RaindropsOnWindshield tem gotas grandes e desfocadas
    (câmera colada no vidro), mas suas máscaras reduzidas ficaram anguladas
    ("flocos") e, quando quase retangulares, deixavam um retângulo de borda
    dura. Por isso o formato principal são elipses irregulares anti-aliased e
    as máscaras entram só como MINORIA (``frac_mascaras``, <= 20%), depois de
    descartar as quase retangulares (preenchimento do bbox > 0,88) e passar por
    :func:`_arredondar_mascara`. Cada forma é um float32 (h, w) em [0, 1], com
    borda de alfa zero.

    Args:
        formas_dir: Diretório com subpastas ``*/`` de PNG binários 0/255 (ou None).
        n_formas: Tamanho total do banco.
        passo_arquivos: Lê 1 a cada N arquivos (máscaras vizinhas são parecidas).
        frac_mascaras: Fração máxima do banco vinda de máscaras reais.

    Returns:
        Lista determinística de formas.
    """
    chave = (str(formas_dir), n_formas, frac_mascaras)
    if chave in _CACHE_BANCO:
        return _CACHE_BANCO[chave]
    n_mask = int(n_formas * min(frac_mascaras, 0.2))
    mascaras: list[np.ndarray] = []
    if n_mask > 0 and formas_dir is not None and Path(formas_dir).is_dir():
        arquivos = sorted(Path(formas_dir).glob("*/*.png"))[:: max(passo_arquivos, 1)]
        for arq in arquivos:
            mascara = cv2.imread(str(arq), cv2.IMREAD_GRAYSCALE)
            if mascara is None or not mascara.any():
                continue
            rotulos, _ = ndi.label(mascara > 127)
            for i, sl in enumerate(ndi.find_objects(rotulos), start=1):
                if sl is None:
                    continue
                comp = rotulos[sl] == i
                h, w = comp.shape
                area = int(comp.sum())
                toca_borda = (
                    sl[0].start == 0
                    or sl[1].start == 0
                    or sl[0].stop == mascara.shape[0]
                    or sl[1].stop == mascara.shape[1]
                )
                if toca_borda or area < 400 or max(h, w) / max(min(h, w), 1) > 2.2:
                    continue
                fill = area / float(h * w)
                if fill < 0.55 or fill > 0.88:  # descarta quase-retângulos e vazados
                    continue
                esc = 56.0 / max(h, w)
                pequena = cv2.resize(
                    comp.astype(np.float32),
                    (max(int(round(w * esc)), 8), max(int(round(h * esc)), 8)),
                    interpolation=cv2.INTER_AREA,
                )
                mascaras.append(_arredondar_mascara(pequena))
            if len(mascaras) >= n_mask:
                break
    mascaras = mascaras[:n_mask]
    elipses = _formas_elipticas(n_formas - len(mascaras), np.random.default_rng(12345))
    formas = elipses + mascaras
    _CACHE_BANCO[chave] = formas
    return formas



# --------------------------------------------------------------------------- #
# Geometria
# --------------------------------------------------------------------------- #
def _mascara_protecao(h: int, w: int, geo: dict[str, Any]) -> np.ndarray:
    """Máscara 1 na cena e 0 no capô/painel (faixa inferior do quadro).

    Por que: o capô está colado na câmera (d ≈ 0), então a névoa não o afeta, e
    gotas/riscos sintéticos sobre o painel denunciariam a montagem.
    Transição suave (smoothstep) para não deixar emenda visível.

    Returns:
        Array float32 (h, w) em [0, 1] (constante por coluna).
    """
    y = (np.arange(h, dtype=np.float32) + 0.5) / h
    ini = geo["capo_y"] - geo["capo_suavizacao"]
    t = np.clip((y - ini) / (2 * geo["capo_suavizacao"]), 0.0, 1.0)
    linha = 1.0 - (t * t * (3 - 2 * t))
    return np.repeat(linha[:, None], w, axis=1).astype(np.float32)


def _mapa_d(h: int, w: int, geo: dict[str, Any], cal: dict[str, Any]) -> np.ndarray:
    """Profundidade relativa por linha, em metros, a partir do horizonte.

    Aproximação do plano de chão: ``d`` cai de ``d_max_m`` (horizonte e acima:
    prédios, céu) a ``d_camera_m`` (capô), com perfil de potência. A lei física
    ``1/(y−y_h)`` foi trocada por este perfil porque gerava uma faixa de névoa
    com emenda visível no horizonte. Sem rede de profundidade.
    """
    y = (np.arange(h, dtype=np.float32) + 0.5) / h
    yh, yc = geo["horizonte_y"], geo["capo_y"]
    # perfil suave: d_max no horizonte e acima, decaindo até d_camera no capô.
    # (a lei 1/(y-y_h) pura cria uma faixa horizontal visível de névoa)
    u = np.clip((yc - y) / (yc - yh), 0.0, 1.0)
    d = cal["d_camera_m"] + (cal["d_max_m"] - cal["d_camera_m"]) * u ** cal["perfil_expoente"]
    return np.repeat(d[:, None], w, axis=1).astype(np.float32)


# --------------------------------------------------------------------------- #
# Camadas
# --------------------------------------------------------------------------- #
def _luz_ar(img: np.ndarray, geo: dict[str, Any], cal: dict[str, Any]) -> np.ndarray:
    """Estima a luz atmosférica A (BGR) a partir do céu da própria base.

    Usa a MÉDIA da faixa superior (não um percentil alto) multiplicada por
    ``luz_ar_fator`` < 1. Por que: chuva forte real (23/09, YouTube) é mais
    escura/acinzentada, não mais clara; uma ``A`` clara faria a névoa embranquecer
    a imagem e o modelo aprenderia "mais claro = mais forte" (atalho de brilho).
    """
    topo = img[: max(int(img.shape[0] * geo["horizonte_y"] * 0.7), 4)]
    a = topo.reshape(-1, 3).mean(axis=0).astype(np.float32)
    a = 0.6 * a + 0.4 * float(a.mean())  # dessatura um pouco
    return np.clip(a * cal["luz_ar_fator"], 0.05, 0.9)


def _camada_nevoa(
    img: np.ndarray,
    mm_alvo: float,
    mm_base: float,
    prot: np.ndarray,
    geo: dict[str, Any],
    cal: dict[str, Any],
    cfg: dict[str, Any],
    fo: dict[str, Any],
    s: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Koschmieder ``I = J·t + A·(1−t)`` com incremento de extinção sobre a base."""
    h, w = img.shape[:2]
    b_alvo = beta_extincao(mm_alvo, cal["beta_gamma_km"], cal["beta_epsilon"])
    b_base = beta_extincao(mm_base, cal["beta_gamma_km"], cal["beta_epsilon"])
    delta_km = max(b_alvo - b_base, 0.0) * cfg["escala_beta"] * (1.0 + fo["beta_extra"] * s)
    d = _mapa_d(h, w, geo, cal) / 1000.0  # km
    t = np.exp(-delta_km * d)[..., None]
    a = _luz_ar(img, geo, cal)
    saida = img * t + a[None, None, :] * (1.0 - t)
    escur = cal["escurecimento_max"] * min(mm_alvo / 40.0, 1.0) + fo["escurecimento_extra"] * s
    saida = saida * (1.0 - escur)
    # chuva forte real é mais cinza: dessatura para a média dos canais (mantém o brilho médio)
    cinza = saida.mean(axis=2, keepdims=True)
    saida = saida + fo["dessaturacao"] * s * (cinza - saida)
    if fo.get("veu", 0.0) > 0:
        media = saida.reshape(-1, 3).mean(axis=0)
        saida = saida + fo["veu"] * s * (media[None, None, :] - saida)
    saida = img + prot[..., None] * (saida - img)
    t_hor = float(np.exp(-delta_km * cal["d_max_m"] / 1000.0))
    return saida, {
        "beta_alvo_km": round(b_alvo, 3),
        "beta_base_km": round(b_base, 3),
        "delta_beta_km": round(delta_km, 3),
        "t_horizonte": round(t_hor, 4),
        "luz_ar_bgr": [round(float(x), 3) for x in a],
    }


def _camada_streaks(
    img: np.ndarray,
    mm_alvo: float,
    prot: np.ndarray,
    cfg: dict[str, Any],
    rng: np.random.Generator,
    escala: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Riscos finos e fracos (screen blend), densidade ∝ mm/h até ``max_streaks``."""
    h, w = img.shape[:2]
    n = int(min(cfg["por_mm_h"] * mm_alvo, cfg["max_streaks"]))
    layer = np.zeros((h, w), np.float32)
    lo, hi = cfg["comprimento_px"]
    ang = np.deg2rad(cfg["angulo_graus"])
    xs = rng.uniform(0, w, n)
    ys = rng.uniform(0, h * 0.85, n)
    comp = rng.uniform(lo, hi, n) * escala * (0.6 + 0.8 * ys / h)
    op = rng.uniform(0.4, 1.0, n)
    for x, y, c, o in zip(xs, ys, comp, op):
        dx, dy = np.sin(ang) * c, np.cos(ang) * c
        cv2.line(
            layer,
            (int(round(x)), int(round(y))),
            (int(round(x + dx)), int(round(y + dy))),
            float(o),
            1,
            cv2.LINE_AA,
        )
    layer = cv2.GaussianBlur(layer, (0, 0), 0.7)
    s = np.clip(layer * cfg["opacidade_max"], 0, 1) * prot
    saida = 1.0 - (1.0 - img) * (1.0 - s[..., None])
    return saida, {"n_streaks": n, "opacidade_max": cfg["opacidade_max"]}


def _ruido_baixa_freq(
    h: int, w: int, escala_px: float, rng: np.random.Generator
) -> np.ndarray:
    """Ruído gaussiano suave normalizado a desvio 1 (campos de película/agrupamento)."""
    r = rng.standard_normal((h, w)).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), max(escala_px, 1.0))
    return r / (float(r.std()) + 1e-6)


def _camada_pelicula(
    img: np.ndarray,
    mm_alvo: float,
    prot: np.ndarray,
    cfg: dict[str, Any],
    rng: np.random.Generator,
    escala: float,
    fo: dict[str, Any],
    s: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Película d'água: regiões com desfoque e distorção suave (remap)."""
    h, w = img.shape[:2]
    frac = float(min(cfg["area_por_mm_h"] * mm_alvo, cfg["area_max"]) + fo["pelicula_area_extra"] * s)
    campo = _ruido_baixa_freq(h, w, cfg["escala_px"] * escala, rng)
    limiar = float(np.quantile(campo, 1.0 - frac)) if frac > 0 else np.inf
    m = np.clip((campo - limiar) / 0.6 + 0.5, 0.0, 1.0)
    m = cv2.GaussianBlur(m, (0, 0), 6.0 * escala) * prot
    # distorção: deslocamento de baixa frequência (a água curva a luz)
    amp = (cfg["distorcao_px"] + fo.get("pelicula_distorcao_extra", 0.0) * s) * escala
    gx = _ruido_baixa_freq(h, w, cfg["distorcao_escala_px"] * escala, rng) * amp
    gy = _ruido_baixa_freq(h, w, cfg["distorcao_escala_px"] * escala, rng) * amp
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    dist = cv2.remap(
        img,
        xx + gx * m,
        yy + gy * m,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    desf = cfg["desfoque_px"] + fo["pelicula_desfoque_extra"] * s
    borr = cv2.GaussianBlur(dist, (0, 0), desf * escala)
    saida = img + m[..., None] * (borr - img)
    return saida, {
        "area_pelicula": round(frac, 4),
        "desfoque_px": round(desf, 3),
        "cobertura_pelicula": round(float((m > 0.5).mean()), 4),
    }


def _campo_densidade(
    h: int, w: int, agrup: float, prot: np.ndarray, rng: np.random.Generator, escala: float,
    varredura: float = 0.0,
) -> np.ndarray:
    """Distribuição de probabilidade de posição das gotas (agrupada e fora do capô)."""
    campo = _ruido_baixa_freq(h, w, 45.0 * escala, rng)
    # só longe do capô: o patch refratado de uma gota na borda herdaria o painel escuro
    p = np.exp(agrup * campo) * (prot > 0.97)
    if varredura > 0:
        # arco central varrido pelo limpador: menos gotas; bordas ficam densas
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r2 = ((xx / w - 0.5) / 0.36) ** 2 + ((yy / h - 0.60) / 0.30) ** 2
        p = p * (1.0 - varredura * np.exp(-(r2**2)))
    return p / p.sum()


def _forma_escorrido(rng: np.random.Generator) -> np.ndarray:
    """Forma de escorrido: cápsula vertical fina, afilada embaixo, anti-aliased."""
    h, w = 64, int(rng.integers(6, 10))
    m = np.zeros((h * 4, w * 4), np.float32)
    cv2.ellipse(m, (w * 2, h * 2), (int(w * 1.6), h * 2 - 6), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    m = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)
    m = cv2.GaussianBlur(m, (0, 0), 0.8)
    return np.pad(m, 1)


def _camada_gotas(
    img: np.ndarray,
    mm_alvo: float,
    mm_base: float,
    prot: np.ndarray,
    cal: dict[str, Any],
    cfg: dict[str, Any],
    rng: np.random.Generator,
    escala: float,
    banco: list[np.ndarray],
    fo: dict[str, Any],
    s: float,
    rng_forte: np.random.Generator,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Gotas por refração, com teto de saturação (limpador).

    A densidade final é ``dens_base·min(mm_alvo/mm_base, teto)``; como a base já
    tem ``dens_base`` gotas, só se desenham as ``dens_base·(razão−1)`` que faltam.

    Em chuva forte (rampa ``s`` > 0) acrescenta-se, com um gerador à parte (a
    moderada não muda): uma cauda de gotas GRANDES e borradas (raio ~4-10 px a
    640 de largura), algumas coalescidas (gotas menores coladas nas grandes) e
    escorridos verticais curtos abaixo delas. Por que: o detector do D6 só vê
    gota pequena e nítida, mas é a água grande/borrada que falta ao forte
    comparado com o YouTube.
    """
    h, w = img.shape[:2]
    mpx = h * w / 1e6
    razao = mm_alvo / max(mm_base, 1e-6)
    razao_ef = min(razao, cfg["teto_saturacao"])
    n_add = int(round(cal["densidade_gotas_base_mpx"] * mpx * max(razao_ef - 1.0, 0.0)))
    info = {
        "razao_mm_h": round(razao, 3),
        "razao_efetiva": round(razao_ef, 3),
        "saturou": bool(razao > cfg["teto_saturacao"]),
        "n_gotas_add": n_add,
        "densidade_final_mpx": round(cal["densidade_gotas_base_mpx"] * razao_ef, 1),
    }
    # lista de gotas: (cx, cy, r, forma, flip, desfoque_px)
    gotas: list[tuple] = []  # (cx, cy, r, forma, flip, desfoque, multiplicador de alfa)
    if n_add > 0:
        pos = _campo_densidade(h, w, cfg["agrupamento"], prot, rng, escala, cfg["varredura_reducao"]).ravel()
        idx = rng.choice(pos.size, size=n_add, p=pos)
        cy, cx = np.divmod(idx, w)
        raio = rng.lognormal(np.log(cfg["raio_mediana_px"] * escala), cfg["raio_sigma"], n_add)
        # cauda de gotas grandes cresce com o mm/h (escorrimento, aglomeração)
        grande = rng.random(n_add) < cfg["cauda_grande_por_mm_h"] * mm_alvo
        raio[grande] *= rng.uniform(1.8, 3.2, int(grande.sum()))
        raio = np.clip(raio, 1.4 * escala, cfg["raio_max_px"] * escala)
        forma_i = rng.integers(0, len(banco), n_add)
        flips = rng.random(n_add) < 0.5
        for k in range(n_add):
            gotas.append((int(cx[k]), int(cy[k]), float(raio[k]), banco[forma_i[k]], bool(flips[k]), cfg["desfoque_gota_px"], 1.0))
        info["raio_medio_px"] = round(float(raio.mean()), 2)

    n_grandes = n_cois = n_escorr = 0
    if s > 0 and fo["gotas_grandes_mpx"] > 0:
        n_grandes = int(round(fo["gotas_grandes_mpx"] * mpx * s))
        pos = _campo_densidade(h, w, 0.3, prot, rng_forte, escala, 0.35).ravel()
        idx = rng_forte.choice(pos.size, size=n_grandes, p=pos)
        gy, gx = np.divmod(idx, w)
        rg = rng_forte.lognormal(np.log(fo["raio_grande_mediana_px"] * escala), fo["raio_grande_sigma"], n_grandes)
        rg = np.clip(rg, fo["raio_grande_min_px"] * escala, fo["raio_grande_max_px"] * escala)
        for k in range(n_grandes):
            forma = banco[int(rng_forte.integers(0, len(banco)))]
            gotas.append((int(gx[k]), int(gy[k]), float(rg[k]), forma, bool(rng_forte.random() < 0.5), fo["desfoque_grande_px"], 1.0))
            if rng_forte.random() < fo["coalescencia_frac"]:  # gotinhas coladas: viram uma só mancha
                for _ in range(int(rng_forte.integers(1, 3))):
                    ang = rng_forte.uniform(0, 2 * np.pi)
                    off = rg[k] * rng_forte.uniform(0.6, 0.95)
                    gotas.append(
                        (int(gx[k] + off * np.cos(ang)), int(gy[k] + off * np.sin(ang)),
                         float(rg[k] * rng_forte.uniform(0.5, 0.8)),
                         banco[int(rng_forte.integers(0, len(banco)))], bool(rng_forte.random() < 0.5),
                         fo["desfoque_grande_px"] * 0.8, 1.0)
                    )
                    n_cois += 1
            if rng_forte.random() < fo["escorridos_frac"]:  # escorrido vertical abaixo da gota
                lo, hi = fo["escorrido_comprimento_px"]
                comp = float(rng_forte.uniform(lo, hi)) * escala
                gotas.append(
                    (int(gx[k]), int(gy[k] + rg[k] + comp / 2), comp / 2, _forma_escorrido(rng_forte), False, 1.0, 0.55)
                )
                n_escorr += 1
    info.update({"n_gotas_grandes": n_grandes, "n_coalescidas": n_cois, "n_escorridos": n_escorr})
    if not gotas:
        info["cobertura_gotas"] = 0.0
        return img, info

    # fundo de onde a gota "enxerga": levemente desfocado, como visto pela lente
    fundo = cv2.GaussianBlur(img, (0, 0), 1.2 * escala)
    pad = int(max(cfg["raio_max_px"], 24.0) * escala * 3) + 8
    fundo_p = cv2.copyMakeBorder(fundo, pad, pad, pad, pad, cv2.BORDER_REFLECT)
    saida = img.copy()
    cob = np.zeros((h, w), np.float32)
    for cx_, cy_, r, forma, flip, desf, amult in gotas:
        if flip:
            forma = forma[:, ::-1]
        fh, fw = forma.shape
        # lado maior = 2r; gotas no vidro vertical tendem a ser mais altas que largas
        sc = 2.0 * r / max(fh, fw)
        gw = max(int(round(fw * sc)), 3)
        gh = max(int(round(fh * sc)), 3)
        alfa = cv2.resize(forma, (gw, gh), interpolation=cv2.INTER_AREA)
        alfa = cv2.GaussianBlur(alfa, (0, 0), 0.5 + 0.25 * desf) if gw > 4 else alfa
        x0, y0 = cx_ - gw // 2, cy_ - gh // 2
        xa, ya = max(x0, 0), max(y0, 0)
        xb, yb = min(x0 + gw, w), min(y0 + gh, h)
        if xb <= xa or yb <= ya or not (0 <= cx_ < w and 0 <= cy_ < h + gh):
            continue
        # patch de origem: campo ~3x maior que a gota, invertido verticalmente
        qx, qy = cx_ + pad, min(max(cy_, 0), h - 1) + pad
        rx, ry = int(gw * 1.6) + 1, int(gh * 1.6) + 1
        patch = fundo_p[qy - ry : qy + ry + 1, qx - rx : qx + rx + 1][::-1]
        patch = cv2.resize(patch, (gw, gh), interpolation=cv2.INTER_AREA)
        patch = cv2.GaussianBlur(patch, (0, 0), desf)
        # interior levemente mais claro que o entorno (a gota concentra a luz)
        patch = np.clip((patch - patch.mean()) * 1.1 + patch.mean() - cfg["escurecimento_gota"] * patch.mean(), 0, 1)
        # recorte do que cabe no quadro
        sub = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
        al = alfa[sub]
        pt = patch[sub]
        # borda escura (anel interno) e brilho especular no canto superior
        nucleo = cv2.erode(alfa, np.ones((3, 3), np.uint8)) if gw > 6 else alfa
        anel = np.clip(alfa - nucleo, 0, 1)[sub]
        yy, xx = np.mgrid[0:gh, 0:gw].astype(np.float32)
        spec = np.exp(-(((xx - gw * 0.35) / (gw * 0.16 + 0.6)) ** 2 + ((yy - gh * 0.3) / (gh * 0.14 + 0.6)) ** 2))
        spec = (spec * alfa)[sub]
        regiao = saida[ya:yb, xa:xb]
        corpo = pt * (1.0 - cfg["borda_escura"] * anel[..., None])
        corpo = corpo + cfg["brilho"] * spec[..., None] * (1.0 - corpo)
        a_ = np.clip(al * 0.9 + anel * 0.1, 0, 1) * prot[ya:yb, xa:xb] * amult
        saida[ya:yb, xa:xb] = regiao + a_[..., None] * (corpo - regiao)
        cob[ya:yb, xa:xb] = np.maximum(cob[ya:yb, xa:xb], a_)
    info["cobertura_gotas"] = round(float((cob > 0.3).mean()), 4)
    return saida, info


# --------------------------------------------------------------------------- #
# API principal
# --------------------------------------------------------------------------- #
def gerar_amostra(
    base_bgr: np.ndarray,
    mm_h_base: float,
    mm_h_alvo: float,
    seed: int,
    config: dict[str, Any] | None = None,
    banco_formas: list[np.ndarray] | None = None,
) -> ResultadoSintetico:
    """Acrescenta chuva a um frame real de garoa.

    Com todas as camadas desligadas devolve a base byte a byte (a conversão
    para float e de volta é exata), o que o teste de regressão exige: fora das
    camadas nada muda.

    Args:
        base_bgr: Frame BGR uint8 de garoa REAL da partição de treino.
        mm_h_base: mm/h medido pela estação para a base (rótulo real).
        mm_h_alvo: Intensidade a simular (moderada ∈ [3,5; 8,5], forte ∈ [12; 40]).
        seed: Semente; mesma seed e mesma base geram a mesma imagem.
        config: Sobrescritas sobre :func:`config_padrao` (normalmente do YAML).
        banco_formas: Banco de formas de gota; se ``None`` é carregado da config.

    Returns:
        :class:`ResultadoSintetico` com a imagem e os parâmetros efetivos.
    """
    cfg = _mesclar(config_padrao(), config)
    geo, cal, cam = cfg["geometria"], cfg["calibracao"], cfg["camadas"]
    h, w = base_bgr.shape[:2]
    escala = w / float(geo["largura_ref"])
    # um sub-gerador por camada: ligar/desligar uma camada não muda as outras
    rngs = {nome: np.random.default_rng([seed, i]) for i, nome in enumerate(CAMADAS)}

    fo = cfg["forte"]
    s = float(np.clip((mm_h_alvo - fo["mm_ini"]) / (fo["mm_fim"] - fo["mm_ini"]), 0.0, 1.0))
    rng_forte = np.random.default_rng([seed, 99])
    img = base_bgr.astype(np.float32) / 255.0
    prot = _mascara_protecao(h, w, geo)
    params: dict[str, Any] = {"mm_h_base": mm_h_base, "mm_h_alvo": mm_h_alvo, "rampa_forte": round(s, 3)}

    if cam["nevoa"]["ativa"]:
        img, params["nevoa"] = _camada_nevoa(img, mm_h_alvo, mm_h_base, prot, geo, cal, cam["nevoa"], fo, s)
    if cam["streaks"]["ativa"]:
        img, params["streaks"] = _camada_streaks(
            img, mm_h_alvo, prot, cam["streaks"], rngs["streaks"], escala
        )
    if cam["pelicula"]["ativa"]:
        img, params["pelicula"] = _camada_pelicula(
            img, mm_h_alvo, prot, cam["pelicula"], rngs["pelicula"], escala, fo, s
        )
    if cam["gotas"]["ativa"]:
        if banco_formas is None:
            g = cam["gotas"]
            banco_formas = carregar_banco_formas(
                _resolver_dir(g["formas_dir"]), g["n_formas"], g["passo_arquivos"]
            )
        img, params["gotas"] = _camada_gotas(
            img, mm_h_alvo, mm_h_base, prot, cal, cam["gotas"], rngs["gotas"], escala, banco_formas, fo, s, rng_forte
        )
    if cam["spray"]["ativa"]:
        raise NotImplementedError("spray fica desligado no v1 (spec D7, camada 5)")

    cg = params.get("gotas", {}).get("cobertura_gotas", 0.0)
    cp = params.get("pelicula", {}).get("cobertura_pelicula", 0.0)
    params["cobertura_agua"] = round(1.0 - (1.0 - cg) * (1.0 - cp), 4)  # união aproximada

    saida = np.clip(np.rint(img * 255.0), 0, 255).astype(np.uint8)
    return ResultadoSintetico(imagem=saida, parametros=params)


def _resolver_dir(caminho: str) -> Path | None:
    """Resolve ``formas_dir`` relativo à raiz do repo (ou ao cwd), tolerando ausência."""
    p = Path(caminho)
    if p.is_absolute():
        return p
    raiz = Path(__file__).resolve().parents[4]  # .../CityRain
    for cand in (raiz / p, Path.cwd() / p):
        if cand.is_dir():
            return cand
    return None
