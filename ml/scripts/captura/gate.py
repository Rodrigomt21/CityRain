"""
gate.py — Ponte fina entre o uploader.py e o gate binário chuva/não-chuva
treinado (~/modelo_chuva/detector.py + bestModel.onnx).

Import isolado de propósito: importar este módulo é leve (só repassa
constantes do detector.py, que por sua vez só usa numpy/PIL no import).
Carregar o modelo de verdade só acontece na primeira chamada de
classificar() — a primeira inferência paga ~14s de inicialização de
contexto CUDA (uma vez só, por vida do processo); as seguintes ficam em
~95-100ms. Não faz sentido pagar esse custo se a fila do uploader estiver
vazia.

Histórico (2026-09-15): a primeira versão usava bestModel.pth via torch,
forçando CPU (usar_gpu=False) porque o wheel de torch instalado (JetPack
4.6.1, kernels CUDA sm_62/sm_72) não cobre a GPU desta Jetson Nano (Tegra
X1, sm_53) — ~2-2,5s/frame, mais lento que a câmera captura (1fps), fila
sem fim. Migrado pra bestModel.onnx + onnxruntime: o wheel onnxruntime-gpu
do Jetson Zoo (compilado pela própria NVIDIA pra esse hardware) roda em
CUDA de verdade nesta GPU — ~95-100ms/frame, sem esse problema. TensorRT
ainda não instalado no sistema (falta rodar apt como sudo — ver
MUDANCAS_NECESSARIAS_BACKEND.md/CLAUDE.md); enquanto isso, onnxruntime cai
sozinho pra CUDAExecutionProvider (que já é rápido o bastante).
"""
import os
import sys

MODELO_DIR = os.path.expanduser("~/modelo_chuva")
if MODELO_DIR not in sys.path:
    sys.path.insert(0, MODELO_DIR)

from detector import DetectorGota, CLASSE_COM_GOTA, CLASSE_SEM_GOTA  # noqa: E402

_detector = None


def _carrega(config):
    global _detector
    if _detector is None:
        caminho_modelo = config.get(
            "modelo_chuva_path", os.path.join(MODELO_DIR, "bestModel.onnx")
        )
        limiar = config.get("limiar_chuva", 0.5)
        # usar_gpu=True: com o motor onnxruntime (ver docstring do módulo),
        # GPU funciona de verdade nesta Jetson. Se o arquivo apontado for um
        # .pth (motor torch), isso NÃO deve ser usado — o wheel de torch
        # instalado não suporta a GPU desta Nano (ver histórico acima).
        _detector = DetectorGota(caminho_modelo, limiar=limiar, usar_gpu=True)
        print(f"[gate] modelo carregado ({_detector.motor.nome}, limiar={limiar})")
    return _detector


def classificar(caminho_jpg, config):
    """Roda o gate numa foto já salva em disco.

    Devolve {'classe': 'com_gota'|'sem_gota', 'probabilidade': float, 'ms': float}.
    Pode levantar exceção (modelo ausente, torch quebrado etc.) — quem chama
    decide o que fazer (uploader.py trata como falha transitória e tenta de
    novo depois, sem derrubar o serviço).
    """
    return _carrega(config).prever(caminho_jpg)
