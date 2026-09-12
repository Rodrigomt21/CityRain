"""
Detector de gota para rodar na Jetson.

Este modulo NAO captura imagem: ele recebe a imagem que o seu codigo de captura
ja produz e devolve o veredito. A ideia e plugar nas duas linhas de codigo que
voce ja tem, sem reescrever o que funciona.

    from detector import DetectorGota

    det = DetectorGota("best_model_tcc.pth")
    r = det.prever(frame)              # frame do OpenCV, PIL, numpy ou caminho
    print(r["classe"], r["probabilidade"])
    det.registrar(r)                   # anexa uma linha no CSV de log

Por que o pre-processamento esta escrito na mao aqui
-----------------------------------------------------
No treino a imagem passou por: PIL em RGB -> redimensionar para 384x384
(bilinear) -> dividir por 255 -> normalizar pela media e desvio do ImageNet.
Se na Jetson qualquer um desses passos sair diferente, o modelo perde precisao
EM SILENCIO - sem erro, sem aviso, so numeros piores.

As duas armadilhas classicas, ambas tratadas aqui:
  - OpenCV entrega BGR, nao RGB. Trocar os canais faz a rede ver outra imagem.
  - torchvision nem sempre existe na Jetson, e versoes diferentes mudam o
    redimensionamento. Por isso o preparo e feito com PIL + NumPy puro, que
    se comportam igual em qualquer versao.

O modulo roda com PyTorch ou com ONNX Runtime, o que estiver instalado.
"""
import csv
import os
import time

import numpy as np
from PIL import Image

# --- constantes congeladas do treino. Nao mexer sem retreinar. ---
RESOLUCAO = 384
MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIO = np.array([0.229, 0.224, 0.225], dtype=np.float32)
LIMIAR_PADRAO = 0.5

CLASSE_COM_GOTA = "com_gota"
CLASSE_SEM_GOTA = "sem_gota"

COLUNAS_LOG = ["timestamp", "arquivo", "classe", "probabilidade", "limiar", "ms"]


# ---------------------------------------------------------------- preparo
def preparar(imagem):
    """Converte qualquer entrada no tensor 1x3x384x384 que o modelo espera.

    Aceita: caminho (str), PIL.Image, ou numpy array. Array de 3 canais vindo
    do OpenCV e tratado como BGR e convertido para RGB - que e o caso normal
    de quem usa cv2.VideoCapture ou cv2.imread.
    """
    if isinstance(imagem, str):
        img = Image.open(imagem).convert("RGB")
    elif isinstance(imagem, Image.Image):
        img = imagem.convert("RGB")
    elif isinstance(imagem, np.ndarray):
        arr = imagem
        if arr.ndim == 2:                       # escala de cinza
            arr = np.stack([arr] * 3, axis=-1)
        elif arr.shape[2] == 4:                 # BGRA do OpenCV
            arr = arr[:, :, :3]
        if arr.shape[2] == 3:
            arr = arr[:, :, ::-1]               # BGR -> RGB
        img = Image.fromarray(arr.astype(np.uint8), "RGB")
    else:
        raise TypeError("imagem deve ser caminho, PIL.Image ou numpy array")

    img = img.resize((RESOLUCAO, RESOLUCAO), Image.BILINEAR)
    x = np.asarray(img, dtype=np.float32) / 255.0      # HWC, 0..1
    x = (x - MEDIA) / DESVIO                           # normalizacao ImageNet
    x = x.transpose(2, 0, 1)                           # CHW
    return np.ascontiguousarray(x[None], dtype=np.float32)   # NCHW


def _softmax(v):
    e = np.exp(v - np.max(v))
    return e / e.sum()


# ---------------------------------------------------------------- motores
class _MotorTorch:
    """Carrega o .pth. Precisa de torch e torchvision na Jetson."""

    nome = "pytorch"

    def __init__(self, caminho_modelo, usar_gpu=True):
        import torch
        import torch.nn as nn
        from torchvision.models import mobilenet_v2

        self._torch = torch
        self.device = torch.device(
            "cuda" if (usar_gpu and torch.cuda.is_available()) else "cpu")

        modelo = mobilenet_v2(weights=None) if _aceita_weights(mobilenet_v2) \
            else mobilenet_v2(pretrained=False)
        modelo.classifier = nn.Sequential(nn.Dropout(0.2),
                                          nn.Linear(modelo.last_channel, 2))
        estado = torch.load(caminho_modelo, map_location=self.device)
        if isinstance(estado, dict) and "state_dict" in estado:
            estado = estado["state_dict"]
        modelo.load_state_dict(estado)
        self.modelo = modelo.to(self.device).eval()

    def inferir(self, x):
        torch = self._torch
        with torch.no_grad():
            t = torch.from_numpy(x).to(self.device)
            saida = self.modelo(t)[0].cpu().numpy()
        return _softmax(saida)


class _MotorOnnx:
    """Carrega um .onnx. Mais leve: nao precisa de torch nem torchvision."""

    nome = "onnxruntime"

    def __init__(self, caminho_modelo, usar_gpu=True):
        import onnxruntime as ort

        provedores = ort.get_available_providers()
        escolhidos = []
        if usar_gpu:
            for p in ("TensorrtExecutionProvider", "CUDAExecutionProvider"):
                if p in provedores:
                    escolhidos.append(p)
        escolhidos.append("CPUExecutionProvider")
        self.sessao = ort.InferenceSession(caminho_modelo, providers=escolhidos)
        self.entrada = self.sessao.get_inputs()[0].name

    def inferir(self, x):
        saida = self.sessao.run(None, {self.entrada: x})[0][0]
        return _softmax(saida)


def _aceita_weights(fn):
    """torchvision novo usa weights=; o antigo (Jetson com JetPack 4) usa pretrained=."""
    try:
        import inspect
        return "weights" in inspect.signature(fn).parameters
    except Exception:
        return False


# ---------------------------------------------------------------- detector
class DetectorGota:
    """Portao: recebe imagem, responde se tem gota no vidro.

    limiar: probabilidade minima para declarar "com gota". O padrao 0.5 e o
    ponto medido no TCC (precisao 99,5% e recall 96,1% na camera do projeto).
    Subir o limiar reduz alarme falso e aumenta gota perdida; a tabela de
    pontos de operacao esta em saidas/resultado_teste.json.
    """

    def __init__(self, caminho_modelo, limiar=LIMIAR_PADRAO,
                 usar_gpu=True, log_csv=None):
        if not os.path.isfile(caminho_modelo):
            raise IOError("modelo nao encontrado: {}".format(caminho_modelo))
        self.caminho_modelo = caminho_modelo
        self.limiar = limiar
        self.log_csv = log_csv

        if caminho_modelo.lower().endswith(".onnx"):
            self.motor = _MotorOnnx(caminho_modelo, usar_gpu)
        else:
            self.motor = _MotorTorch(caminho_modelo, usar_gpu)

    def prever(self, imagem, nome=None):
        """Devolve dict com classe, probabilidade de gota e tempo gasto."""
        t0 = time.time()
        probs = self.motor.inferir(preparar(imagem))
        p_gota = float(probs[1])
        ms = (time.time() - t0) * 1000.0

        if nome is None:
            nome = imagem if isinstance(imagem, str) else "(memoria)"

        return {
            "arquivo": os.path.basename(nome) if isinstance(nome, str) else str(nome),
            "tem_gota": p_gota >= self.limiar,
            "classe": CLASSE_COM_GOTA if p_gota >= self.limiar else CLASSE_SEM_GOTA,
            "probabilidade": p_gota,
            "limiar": self.limiar,
            "ms": ms,
        }

    def registrar(self, resultado, caminho=None):
        """Anexa uma linha no CSV de log, criando o cabecalho na primeira vez."""
        destino = caminho or self.log_csv
        if not destino:
            return None
        novo = not os.path.isfile(destino)
        pasta = os.path.dirname(os.path.abspath(destino))
        if pasta and not os.path.isdir(pasta):
            os.makedirs(pasta)
        with open(destino, "a", newline="") as f:
            w = csv.writer(f)
            if novo:
                w.writerow(COLUNAS_LOG)
            w.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                resultado["arquivo"],
                resultado["classe"],
                "{:.6f}".format(resultado["probabilidade"]),
                resultado["limiar"],
                "{:.1f}".format(resultado["ms"]),
            ])
        return destino


# ---------------------------------------------------------------- teste rapido
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Classifica uma imagem na Jetson")
    ap.add_argument("imagem", help="caminho da foto")
    ap.add_argument("--modelo", default="best_model_tcc.pth")
    ap.add_argument("--limiar", type=float, default=LIMIAR_PADRAO)
    ap.add_argument("--log", default="deteccoes.csv")
    ap.add_argument("--cpu", action="store_true", help="forcar CPU")
    args = ap.parse_args()

    det = DetectorGota(args.modelo, limiar=args.limiar,
                       usar_gpu=not args.cpu, log_csv=args.log)
    print("motor: {}".format(det.motor.nome))

    r = det.prever(args.imagem)
    print("{:<28} {:<9} {:6.2f}%   {:5.0f} ms".format(
        r["arquivo"], r["classe"], 100 * r["probabilidade"], r["ms"]))
    print("log: {}".format(det.registrar(r)))
