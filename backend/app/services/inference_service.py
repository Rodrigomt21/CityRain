"""
Serviço de inferência do backend — classifica intensidade de chuva.

Há dois modelos: o móvel (garoa/moderado/forte), pois a Jetson filtra capturas
secas antes do envio (gate binário chuva/não-chuva); e o de câmera fixa, que
recebe todos os quadros e por isso também pode devolver ``seco``. O modelo fixo
pode usar 6 canais (imagem + referência seca da mesma câmera e período). O
``RoteadorInferencia`` escolhe o modelo pelo tipo do dispositivo.

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
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

# Labels do modelo móvel — ele nunca devolve "seco" (a Jetson já filtrou essas capturas);
# o modelo de câmera fixa pode devolver "seco".
RAIN_LABELS = ("garoa", "moderado", "forte")

# Vocabulário do ML -> vocabulário do banco. O ML usa "moderada"; o banco, "moderado".
_ML_PARA_BANCO = {"seco": "seco", "garoa": "garoa", "moderada": "moderado", "moderado": "moderado", "forte": "forte"}

MODELOS_DIR = Path(__file__).resolve().parent.parent / "inference" / "modelos"
MODELO_PADRAO = MODELOS_DIR / "intensidade.onnx"
MODELO_FIXA_PADRAO = MODELOS_DIR / "intensidade_fixa.onnx"
REFERENCIAS_PADRAO = Path(__file__).resolve().parent.parent / "inference" / "referencias"


class Classificacao(NamedTuple):
    """Resultado de uma inferência. Tudo None = intensidade não medida."""

    label: Optional[str]
    confianca: Optional[float]
    modelo: Optional[str]
    versao: Optional[str]

    @classmethod
    def vazia(cls) -> "Classificacao":
        return cls(None, None, None, None)


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
        self.canais = int(meta.get("canais_entrada", "3"))
        self.experimento = meta.get("experimento")
        self.versao = f"ep{meta['epoca']}" if meta.get("epoca") else None
        self.entrada = self.sessao.get_inputs()[0].name
        self.descricao = f"{meta.get('experimento', '?')} (época {meta.get('epoca', '?')})"

    def _uma(self, image_bytes: bytes):
        """Igual a ``cityrain_ml.data.intensidade.preparar``: RGB -> resize bilinear -> /255 -> ImageNet."""
        from PIL import Image

        np = self._np
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((self.largura, self.altura), Image.BILINEAR)
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = (x - self.media) / self.desvio
        return x.transpose(2, 0, 1)

    def preparar(self, image_bytes: bytes, referencia_bytes: Optional[bytes] = None):
        """Tensor 1×C×H×W; com 6 canais, imagem e referência concatenadas nos canais."""
        np = self._np
        partes = [self._uma(image_bytes)]
        if self.canais == 6:
            if referencia_bytes is None:
                raise ValueError("modelo de 6 canais exige imagem de referência")
            partes.append(self._uma(referencia_bytes))
        return np.ascontiguousarray(np.concatenate(partes, axis=0))[None]

    def prever(self, image_bytes: bytes, referencia_bytes: Optional[bytes] = None) -> tuple[str, float]:
        np = self._np
        logits = self.sessao.run(None, {self.entrada: self.preparar(image_bytes, referencia_bytes)})[0][0]
        p = np.exp(logits - logits.max())
        p /= p.sum()
        k = int(p.argmax())
        return self.classes[k], float(p[k])


class InferenceService:
    """Classifica intensidade de chuva (garoa/moderado/forte) a partir dos bytes da imagem."""

    def __init__(
        self,
        caminho_modelo: Optional[Path] = None,
        padrao: Path = MODELO_PADRAO,
        config_attr: str = "inference_model_path",
    ) -> None:
        self._model: Optional[_ModeloOnnx] = None
        self._avisou_sem_modelo = False
        self._padrao, self._config_attr = padrao, config_attr
        self.carregar(caminho_modelo)

    def carregar(self, caminho_modelo: Optional[Path] = None) -> None:
        """Carrega o .onnx; qualquer falha deixa o serviço sem modelo (intensidade nula), sem derrubar o app."""
        from app.core.config import settings

        caminho = Path(caminho_modelo or getattr(settings, self._config_attr) or self._padrao)
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

    @property
    def exige_referencia(self) -> bool:
        """True quando o modelo carregado espera imagem + referência seca (6 canais)."""
        return self._model is not None and self._model.canais == 6

    async def classificar(self, image_bytes: bytes, referencia_bytes: Optional[bytes] = None) -> Classificacao:
        """Como ``classify``, devolvendo também qual modelo classificou."""
        if self._model is None:
            # Log uma vez por processo: sem isso, cada captura gera uma linha
            # idêntica e o aviso se perde no volume de ingestão.
            if not self._avisou_sem_modelo:
                logger.warning("Nenhum modelo carregado — capturas ficam com weather_label=None (não medido).")
                self._avisou_sem_modelo = True
            return Classificacao.vazia()
        if self.exige_referencia and referencia_bytes is None:
            logger.warning("Modelo %s exige referência e nenhuma foi encontrada", self._model.experimento)
            return Classificacao.vazia()
        try:
            # ~50 ms de CPU: fora do event loop para não travar as outras requisições
            label, conf = await asyncio.to_thread(self._model.prever, image_bytes, referencia_bytes)
        except Exception:  # noqa: BLE001 — imagem corrompida vira "não medida", não 500
            logger.exception("Falha ao classificar imagem (%d bytes)", len(image_bytes))
            return Classificacao.vazia()
        return Classificacao(label, conf, self._model.experimento, self._model.versao)

    async def classify(self, image_bytes: bytes) -> tuple[Optional[str], Optional[float]]:
        """Compatibilidade: (weather_label, confidence). Ver ``classificar``."""
        c = await self.classificar(image_bytes)
        return c.label, c.confianca


class RoteadorInferencia:
    """Escolhe o modelo pelo tipo do dispositivo e, para câmera fixa, a referência seca."""

    def __init__(self, movel: InferenceService, fixa: InferenceService, referencias_dir: Path) -> None:
        self.movel, self.fixa, self.referencias_dir = movel, fixa, Path(referencias_dir)

    def referencia(self, device_name: Optional[str], quando: datetime) -> Optional[bytes]:
        """``<dir>/<device>/<periodo>.jpg``; cai para o outro período se faltar."""
        from app.services.periodo import periodo_local

        if not device_name:
            return None
        pasta = self.referencias_dir / device_name
        periodo = periodo_local(quando)
        for p in (periodo, "noite" if periodo == "dia" else "dia"):
            arq = pasta / f"{p}.jpg"
            if arq.is_file():
                return arq.read_bytes()
        return None

    async def classificar(
        self, image_bytes: bytes, tipo: str, device_name: Optional[str], quando: datetime
    ) -> Classificacao:
        if tipo != "fixa":
            return await self.movel.classificar(image_bytes)
        ref = self.referencia(device_name, quando) if self.fixa.exige_referencia else None
        return await self.fixa.classificar(image_bytes, ref)


def _referencias_dir() -> Path:
    from app.core.config import settings

    return Path(settings.referencias_dir) if settings.referencias_dir else REFERENCIAS_PADRAO


# Singletons: uma instância compartilhada por todas as requisições.
inference_service = InferenceService()
inference_service_fixa = InferenceService(padrao=MODELO_FIXA_PADRAO, config_attr="inference_model_fixa_path")
roteador_inferencia = RoteadorInferencia(inference_service, inference_service_fixa, _referencias_dir())
