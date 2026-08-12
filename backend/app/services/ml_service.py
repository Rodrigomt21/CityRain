"""
Utilitário de reavaliação offline — NÃO faz parte do fluxo de ingestão.

O modelo CNN roda na NVIDIA Jetson (borda) e envia weather_label + confidence
já classificados junto com cada imagem. Este módulo existe somente para
re-executar inferência em capturas já armazenadas durante experimentos de
retreinamento ou validação cruzada do modelo.

Uso:
    python -m app.services.ml_service --capture-id 42
"""

from app.core.database import AsyncSessionLocal
from app.models.capture import Capture


async def reavaliar_captura(capture_id: int, image_path: str) -> None:
    """
    Re-executa a CNN do servidor sobre uma imagem já armazenada e sobrescreve
    weather_label e confidence. Usado apenas para validação offline do modelo.

    Não é chamado durante a ingestão normal — a Jetson já envia esses valores.
    """
    try:
        from ml.predict import predict_weather
    except ImportError:
        return

    result = await predict_weather(image_path)
    if result is None:
        return

    label, confidence = result

    async with AsyncSessionLocal() as session:
        row = await session.get(Capture, capture_id)
        if row:
            row.weather_label = label
            row.confidence = confidence
            await session.commit()
