"""
Serviço de inferência do backend — classifica intensidade de chuva em garoa/moderado/forte.

A Jetson filtra capturas secas antes do envio (gate binário chuva/não-chuva).
Este serviço recebe apenas imagens com chuva confirmada e estima a intensidade.

O modelo é o ONNX exportado por ``ml/scripts/treino/exportar_onnx.py``. O
pré-processamento (classes, altura, largura, média, desvio) vem dos
``metadata_props`` do próprio .onnx — não há constante duplicada aqui para sair
de sincronia com o treino.

Enquanto nenhum modelo estiver carregado, `classify` devolve (None, None) —
"intensidade não medida". Não devolve um rótulo padrão: um valor inventado
viraria dado de dashboard e de dataset indistinguível de medida real.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Labels possíveis — "seco" nunca é retornado aqui; a Jetson já filtrou essas capturas.
RAIN_LABELS = ("garoa", "moderado", "forte")

# Vocabulário do ML -> vocabulário do banco. O ML usa "moderada"; o banco, "moderado".
_ML_PARA_BANCO = {"garoa": "garoa", "moderada": "moderado", "moderado": "moderado", "forte": "forte"}

MODELO_PADRAO = Path(__file__).resolve().parent.parent / "inference" / "modelos" / "intensidade.onnx"


class _ModeloOnnx:
    """Sessão ONNX + pré-processamento lido dos metadados do arquivo."""

    def __init__(self, caminho: Path) -> None:
        import numpy as np
        import onnxruntime as ort

        self._np = np
        self.sessao = ort.InferenceSession(str(caminho), providers=["CPUExecutionProvider"])
        meta = self.sessao.get_modelmeta().custom_metadata_map
        self.classes = [_ML_PARA_BANCO[c] for c in json.loads(meta["classes"])]
        self.altura, self.largura = int(meta["altura"]), int(meta["largura"])
        self.media = np.array(json.loads(meta["media"]), dtype=np.float32)
        self.desvio = np.array(json.loads(meta["desvio"]), dtype=np.float32)
        self.entrada = self.sessao.get_inputs()[0].name
        self.descricao = f"{meta.get('experimento', '?')} (época {meta.get('epoca', '?')})"

    def preparar(self, image_bytes: bytes):
        """Igual a ``cityrain_ml.data.intensidade.preparar``: RGB -> resize bilinear -> /255 -> ImageNet."""
        from PIL import Image

        np = self._np
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((self.largura, self.altura), Image.BILINEAR)
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = (x - self.media) / self.desvio
        return np.ascontiguousarray(x.transpose(2, 0, 1))[None]

    def prever(self, image_bytes: bytes) -> tuple[str, float]:
        np = self._np
        logits = self.sessao.run(None, {self.entrada: self.preparar(image_bytes)})[0][0]
        p = np.exp(logits - logits.max())
        p /= p.sum()
        k = int(p.argmax())
        return self.classes[k], float(p[k])


class InferenceService:
    """Classifica intensidade de chuva (garoa/moderado/forte) a partir dos bytes da imagem."""

    def __init__(self, caminho_modelo: Optional[Path] = None) -> None:
        self._model: Optional[_ModeloOnnx] = None
        self._avisou_sem_modelo = False
        self.carregar(caminho_modelo)

    def carregar(self, caminho_modelo: Optional[Path] = None) -> None:
        """Carrega o .onnx; qualquer falha deixa o serviço sem modelo (intensidade nula), sem derrubar o app."""
        from app.core.config import settings

        caminho = Path(caminho_modelo or settings.inference_model_path or MODELO_PADRAO)
        if not caminho.is_file():
            logger.warning("Modelo de intensidade não encontrado em %s", caminho)
            return
        try:
            self._model = _ModeloOnnx(caminho)
            logger.info("Modelo de intensidade carregado: %s — %s", caminho.name, self._model.descricao)
        except Exception:  # noqa: BLE001 — modelo quebrado não pode impedir a ingestão
            logger.exception("Falha ao carregar o modelo de intensidade %s", caminho)
            self._model = None

    @property
    def disponivel(self) -> bool:
        """True quando há modelo de intensidade carregado."""
        return self._model is not None

    async def classify(self, image_bytes: bytes) -> tuple[Optional[str], Optional[float]]:
        """
        Retorna (weather_label, confidence) para a imagem recebida.

        Sem modelo carregado, ou se a imagem não puder ser lida, retorna
        (None, None): a captura é persistida com intensidade não medida e a
        ingestão não é bloqueada.

        Args:
            image_bytes: Bytes brutos da imagem JPEG/PNG.

        Returns:
            (label, confidence) com label em RAIN_LABELS e confidence em [0, 1],
            ou (None, None) quando não há classificação.
        """
        if self._model is None:
            # Log uma vez por processo: sem isso, cada captura gera uma linha
            # idêntica e o aviso se perde no volume de ingestão.
            if not self._avisou_sem_modelo:
                logger.warning(
                    "Nenhum modelo de intensidade carregado — capturas serão "
                    "persistidas com weather_label=None (intensidade não medida)."
                )
                self._avisou_sem_modelo = True
            return None, None

        try:
            # ~50 ms de CPU: fora do event loop para não travar as outras requisições
            return await asyncio.to_thread(self._model.prever, image_bytes)
        except Exception:  # noqa: BLE001 — imagem corrompida vira "não medida", não 500
            logger.exception("Falha ao classificar imagem (%d bytes)", len(image_bytes))
            return None, None


# Singleton: uma instância compartilhada por todas as requisições.
inference_service = InferenceService()
