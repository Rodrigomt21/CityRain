"""Testes do script de normalização de orientação da coleta própria.

Usa imagens sintéticas assimétricas (quadrante superior-esquerdo vermelho,
resto preto) para poder afirmar rotação por pixel. Ver
docs/specs/spec-normalizacao-orientacao.md.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

# O script vive fora de um pacote Python instalável (ml/scripts/preprocessamento/
# não tem __init__.py nem há pyproject.toml no subprojeto ml/ ainda), então
# carregamos o módulo diretamente do arquivo pelo caminho.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "preprocessamento"
    / "normalizar_orientacao.py"
)
_spec = importlib.util.spec_from_file_location("normalizar_orientacao", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
norm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = norm
_spec.loader.exec_module(norm)


IMG_W, IMG_H = 40, 30


def _make_asymmetric_image(path: Path) -> None:
    """Cria um jpg sintético: quadrante superior-esquerdo vermelho, resto preto."""
    im = Image.new("RGB", (IMG_W, IMG_H), color=(0, 0, 0))
    px = im.load()
    for y in range(IMG_H // 2):
        for x in range(IMG_W // 2):
            px[x, y] = (255, 0, 0)
    im.save(path, format="JPEG", quality=95)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_reddish(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    return r > 150 and g < 100 and b < 100


def _is_blackish(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    return r < 100 and g < 100 and b < 100


# ---------------------------------------------------------------------------
# 1. Rotação 180° move o quadrante vermelho para o inferior-direito.
# ---------------------------------------------------------------------------


def test_rotacao_180_move_quadrante_e_preserva_dimensoes(tmp_path: Path) -> None:
    src = tmp_path / "origem.jpg"
    dest = tmp_path / "destino.jpg"
    _make_asymmetric_image(src)

    norm._write_jpg(src, dest, rotacao=180)

    with Image.open(src) as im_src, Image.open(dest) as im_dest:
        assert im_dest.size == im_src.size
        im_dest_rgb = im_dest.convert("RGB")

        # Quadrante inferior-direito deve estar vermelho após a rotação de 180°.
        assert _is_reddish(im_dest_rgb.getpixel((IMG_W - 2, IMG_H - 2)))
        # Quadrante superior-esquerdo (onde estava o vermelho) deve estar preto.
        assert _is_blackish(im_dest_rgb.getpixel((1, 1)))


# ---------------------------------------------------------------------------
# 2. Rotação 0° produz cópia byte-idêntica.
# ---------------------------------------------------------------------------


def test_rotacao_0_produz_copia_byte_identica(tmp_path: Path) -> None:
    src = tmp_path / "origem.jpg"
    dest = tmp_path / "destino.jpg"
    _make_asymmetric_image(src)

    norm._write_jpg(src, dest, rotacao=0)

    assert _sha256(dest) == _sha256(src)


# ---------------------------------------------------------------------------
# Helpers para montar uma pasta de entrada fake e rodar process_pasta().
# ---------------------------------------------------------------------------


def _build_pasta_com_metadados(
    raiz_entrada: Path,
    nome: str,
    pares_validos: list[str],
    zero_byte: list[str] | None = None,
    json_orfao: list[str] | None = None,
) -> None:
    """Monta `<raiz_entrada>/<nome>/` com pares jpg+json válidos e casos de lixo."""
    pasta = raiz_entrada / nome
    pasta.mkdir(parents=True, exist_ok=True)

    for stem in pares_validos:
        _make_asymmetric_image(pasta / f"{stem}.jpg")
        (pasta / f"{stem}.json").write_text('{"schema": 1}', encoding="utf-8")

    for stem in zero_byte or []:
        (pasta / f"{stem}.jpg").touch()  # 0 byte

    for stem in json_orfao or []:
        (pasta / f"{stem}.json").write_text('{"schema": 1}', encoding="utf-8")


def _default_config_entry(rotacao: int = 180) -> dict:
    return {"rotacao_graus": rotacao}


# ---------------------------------------------------------------------------
# 3. Jpg de 0 byte é pulado e aparece no relatório com motivo zero_byte.
# ---------------------------------------------------------------------------


def test_jpg_zero_byte_e_pulado_e_reportado(tmp_path: Path) -> None:
    raiz_entrada = tmp_path / "raw"
    raiz_saida = tmp_path / "processed"
    _build_pasta_com_metadados(
        raiz_entrada, "pasta_a", pares_validos=["f1"], zero_byte=["f2"]
    )

    report = norm.process_pasta(
        nome="pasta_a",
        cfg_entry=_default_config_entry(180),
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=False,
        force=False,
    )

    motivos = {p.motivo for p in report.pulados if p.arquivo == "f2.jpg"}
    assert motivos == {"zero_byte"}
    assert report.total_entrada == 2  # f1.jpg + f2.jpg (0 byte)
    assert report.total_saida == 1  # só f1 foi copiado


# ---------------------------------------------------------------------------
# 4. Json órfão é pulado e reportado; jpg+json válidos saem juntos.
# ---------------------------------------------------------------------------


def test_json_orfao_e_pulado_e_par_valido_sai_completo(tmp_path: Path) -> None:
    raiz_entrada = tmp_path / "raw"
    raiz_saida = tmp_path / "processed"
    _build_pasta_com_metadados(
        raiz_entrada,
        "pasta_b",
        pares_validos=["f1", "f2"],
        json_orfao=["orfao"],
    )

    report = norm.process_pasta(
        nome="pasta_b",
        cfg_entry=_default_config_entry(180),
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=False,
        force=False,
    )

    orfaos = [p for p in report.pulados if p.motivo == "json_orfao"]
    assert len(orfaos) == 1
    assert orfaos[0].arquivo == "orfao.json"

    saida = raiz_saida / "pasta_b"
    assert (saida / "f1.jpg").exists()
    assert (saida / "f1.json").exists()
    assert (saida / "f2.jpg").exists()
    assert (saida / "f2.json").exists()
    assert not (saida / "orfao.json").exists()
    assert report.total_saida == 2
    assert report.total_json_saida == 2


# ---------------------------------------------------------------------------
# 5. Segunda execução sem --force não reescreve nada (mtime inalterado) e
#    contabiliza ja_existia; com --force, reescreve.
# ---------------------------------------------------------------------------


def test_reexecucao_sem_force_nao_reescreve_com_force_reescreve(tmp_path: Path) -> None:
    raiz_entrada = tmp_path / "raw"
    raiz_saida = tmp_path / "processed"
    _build_pasta_com_metadados(raiz_entrada, "pasta_c", pares_validos=["f1"])

    cfg = _default_config_entry(180)

    report1 = norm.process_pasta(
        nome="pasta_c",
        cfg_entry=cfg,
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=False,
        force=False,
    )
    assert report1.processados == 1
    assert report1.ja_existia == 0

    jpg_saida = raiz_saida / "pasta_c" / "f1.jpg"
    mtime_antes = jpg_saida.stat().st_mtime_ns

    time.sleep(0.05)

    report2 = norm.process_pasta(
        nome="pasta_c",
        cfg_entry=cfg,
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=False,
        force=False,
    )
    assert report2.processados == 0
    assert report2.ja_existia == 1
    assert jpg_saida.stat().st_mtime_ns == mtime_antes  # mtime inalterado

    time.sleep(0.05)

    report3 = norm.process_pasta(
        nome="pasta_c",
        cfg_entry=cfg,
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=False,
        force=True,
    )
    assert report3.processados == 1
    assert report3.ja_existia == 0
    assert jpg_saida.stat().st_mtime_ns != mtime_antes  # foi reescrito


# ---------------------------------------------------------------------------
# 6. --dry-run não cria nenhum arquivo.
# ---------------------------------------------------------------------------


def test_dry_run_nao_cria_nenhum_arquivo(tmp_path: Path) -> None:
    raiz_entrada = tmp_path / "raw"
    raiz_saida = tmp_path / "processed"
    _build_pasta_com_metadados(
        raiz_entrada,
        "pasta_d",
        pares_validos=["f1", "f2"],
        zero_byte=["f3"],
        json_orfao=["orfao"],
    )

    report = norm.process_pasta(
        nome="pasta_d",
        cfg_entry=_default_config_entry(180),
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=True,
        force=False,
    )

    assert not raiz_saida.exists()
    assert report.processados == 2
    assert report.total_entrada == 3


# ---------------------------------------------------------------------------
# Extras: rotação 0° em pasta com subpasta_jpgs (caso framesSemNada) e
# proteção contra escrita em raiz_entrada.
# ---------------------------------------------------------------------------


def test_pasta_sem_metadados_com_subpasta_jpgs(tmp_path: Path) -> None:
    raiz_entrada = tmp_path / "raw"
    raiz_saida = tmp_path / "processed"
    pasta = raiz_entrada / "pasta_e" / "frames"
    pasta.mkdir(parents=True)
    _make_asymmetric_image(pasta / "g1.jpg")
    (pasta / "g2.jpg").touch()  # 0 byte

    report = norm.process_pasta(
        nome="pasta_e",
        cfg_entry={"rotacao_graus": 0, "subpasta_jpgs": "frames"},
        raiz_entrada=raiz_entrada,
        raiz_saida=raiz_saida,
        config_hash="deadbeef",
        dry_run=False,
        force=False,
    )

    saida = raiz_saida / "pasta_e"
    assert (saida / "g1.jpg").exists()
    assert not (saida / "g2.jpg").exists()
    assert not (saida / "frames").exists()  # saída é achatada
    assert report.total_saida == 1
    assert report.total_json_saida == 0
    assert any(p.motivo == "zero_byte" for p in report.pulados)


def test_assert_not_inside_bloqueia_escrita_em_raiz_entrada(tmp_path: Path) -> None:
    raiz_entrada = tmp_path / "raw"
    raiz_entrada.mkdir()

    with pytest.raises(RuntimeError):
        norm.assert_not_inside(raiz_entrada / "subdir" / "arquivo.jpg", raiz_entrada)

    # Caminho fora de raiz_entrada não deve levantar erro.
    norm.assert_not_inside(tmp_path / "processed" / "arquivo.jpg", raiz_entrada)
