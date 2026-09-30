"""
Serviço de inferência do backend — classifica intensidade de chuva em garoa/moderado/forte.

A Jetson filtra capturas secas antes do envio (modelo binário chuva/não-chuva).
Este serviço recebe apenas imagens com chuva confirmada e determina a intensidade.

Para integrar o modelo ONNX exportado pelo ml/, substitua o TODO abaixo.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Labels possíveis — "seco" nunca é retornado aqui; a Jetson já filtrou essas capturas.
RAIN_LABELS = ("garoa", "moderado", "forte")
_DEFAULT_LABEL = "garoa"


class InferenceService:
    """Classifica intensidade de chuva (garoa/moderado/forte) a partir dos bytes da imagem."""

    def __init__(self) -> None:
        self._model = None
        # TODO: carregar modelo ONNX via settings.inference_model_path
        # Exemplo:
        #   import onnxruntime as ort
        #   self._model = ort.InferenceSession(settings.inference_model_path)

    async def classify(self, image_bytes: bytes) -> tuple[str, Optional[float]]:
        """
        Retorna (weather_label, confidence) para a imagem recebida.

        Enquanto nenhum modelo ONNX estiver configurado, retorna o label padrão
        com confidence=None para não bloquear o pipeline de ingestão.

        Args:
            image_bytes: Bytes brutos da imagem JPEG/PNG.

        Returns:
            Tupla (label, confidence). label é um de RAIN_LABELS.
            confidence é None se o modelo não estiver disponível.
        """
        if self._model is None:
            logger.warning(
                "Modelo de inferência não carregado — usando label padrão '%s'.",
                _DEFAULT_LABEL,
            )
            return _DEFAULT_LABEL, None

        # TODO: pré-processar imagem, rodar sessão ONNX, retornar argmax + softmax
        raise NotImplementedError("Inferência ONNX não implementada.")


# Singleton: uma instância compartilhada por todas as requisições.
inference_service = InferenceService()
