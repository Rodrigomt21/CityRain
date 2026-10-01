"""
Serviço de inferência do backend — classifica intensidade de chuva em garoa/moderado/forte.

A Jetson filtra capturas secas antes do envio (gate binário chuva/não-chuva).
Este serviço recebe apenas imagens com chuva confirmada e estima a intensidade.

Enquanto nenhum modelo estiver carregado, `classify` devolve (None, None) —
"intensidade não medida". Não devolve um rótulo padrão: um valor inventado
viraria dado de dashboard e de dataset indistinguível de medida real.

Para integrar o modelo ONNX exportado pelo ml/, substitua o TODO abaixo.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Labels possíveis — "seco" nunca é retornado aqui; a Jetson já filtrou essas capturas.
RAIN_LABELS = ("garoa", "moderado", "forte")


class InferenceService:
    """Classifica intensidade de chuva (garoa/moderado/forte) a partir dos bytes da imagem."""

    def __init__(self) -> None:
        self._model = None
        self._avisou_sem_modelo = False
        # TODO: carregar modelo ONNX via settings.inference_model_path
        # Exemplo:
        #   import onnxruntime as ort
        #   self._model = ort.InferenceSession(settings.inference_model_path)

    @property
    def disponivel(self) -> bool:
        """True quando há modelo de intensidade carregado."""
        return self._model is not None

    async def classify(self, image_bytes: bytes) -> tuple[Optional[str], Optional[float]]:
        """
        Retorna (weather_label, confidence) para a imagem recebida.

        Sem modelo carregado, retorna (None, None): a captura é persistida com
        intensidade não medida, e a ingestão não é bloqueada. Devolver um rótulo
        padrão seria pior que não medir — ele entraria no banco, no mapa de calor
        e no dataset como se fosse classificação, sem nenhuma forma de distinguir.

        Args:
            image_bytes: Bytes brutos da imagem JPEG/PNG.

        Returns:
            (label, confidence) com label em RAIN_LABELS e confidence em [0, 1],
            ou (None, None) quando não há modelo de intensidade disponível.
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

        # TODO: pré-processar imagem, rodar sessão ONNX, retornar argmax + softmax
        raise NotImplementedError("Inferência ONNX não implementada.")


# Singleton: uma instância compartilhada por todas as requisições.
inference_service = InferenceService()
