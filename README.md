# Rodando o detector na Jetson

Esta pasta é tudo que precisa ir pra Jetson: **dois arquivos**.

```
detector.py          o módulo de inferência
best_model_tcc.pth   os pesos treinados (9 MB)
```

O módulo **não captura imagem** — ele recebe a imagem que o seu código de captura já
produz e devolve o veredito. A ideia é plugar no que já funciona, não reescrever.

---

## Como plugar no seu código de captura

```python
from detector import DetectorGota

det = DetectorGota("best_model_tcc.pth", log_csv="deteccoes.csv")

# ... seu código que já captura ...
frame = sua_captura()            # cv2, PIL, numpy ou caminho de arquivo

r = det.prever(frame)
det.registrar(r)

if r["tem_gota"]:
    manda_pro_backend(frame)     # o portão: só sobe o que tem gota
```

O `prever()` devolve:

```python
{
  "arquivo": "frame_001.jpg",
  "tem_gota": True,
  "classe": "com_gota",
  "probabilidade": 0.9994,    # probabilidade de haver gota
  "limiar": 0.5,
  "ms": 41.2                  # tempo de inferência
}
```

Para testar sem escrever código:

```bash
python3 detector.py foto.jpg --modelo best_model_tcc.pth
```

---

## O que ele aceita como entrada

| entrada | tratamento |
|---|---|
| caminho de arquivo (`str`) | abre com PIL em RGB |
| `PIL.Image` | converte pra RGB |
| `numpy` de 3 canais | **tratado como BGR** e convertido pra RGB — é o caso do OpenCV |
| `numpy` de 4 canais (BGRA) | descarta o alfa, mesmo tratamento |
| `numpy` 2D (cinza) | replica nos 3 canais |

Se o seu código já entrega RGB em numpy (raro — quase todo mundo usa OpenCV, que é
BGR), converta antes com `frame[:, :, ::-1]`, senão os canais saem trocados.

---

## Por que o pré-processamento está escrito na mão

No treino a imagem passou por: PIL em RGB → redimensionar pra 384×384 bilinear →
dividir por 255 → normalizar pela média e desvio do ImageNet. Se qualquer um desses
passos sair diferente na Jetson, **o modelo perde precisão em silêncio** — sem erro,
sem aviso, só números piores.

Por isso o preparo aqui usa PIL + NumPy puro, sem `torchvision`: além de ser uma
dependência a menos, versões diferentes do torchvision mudam detalhes do
redimensionamento.

Essa equivalência foi **verificada, não assumida**: comparando o tensor produzido aqui
com o produzido pelo pipeline de treino, a diferença máxima é `0.00e+00` — bit a bit
idêntico. O caminho do OpenCV (BGR) também. Ou seja, os 97,18% de acurácia medidos no
TCC são o que a Jetson reproduz.

---

## Instalação

O módulo roda com **PyTorch** ou com **ONNX Runtime** — o que estiver disponível. Ele
escolhe sozinho pela extensão do arquivo de modelo (`.pth` → PyTorch, `.onnx` → ONNX).

Primeiro descubra o que a placa já tem:

```bash
cat /etc/nv_tegra_release; python3 -V; python3 -c "import torch,torchvision;print(torch.__version__, torch.cuda.is_available())"
```

**Se o PyTorch já responde** — não precisa instalar nada além de `pillow` e `numpy`,
que quase sempre já estão:

```bash
pip3 install --user pillow numpy
```

**Se não tiver PyTorch**, há dois caminhos:

1. *Wheel da NVIDIA* — o PyTorch de PC não funciona no Jetson (arquitetura ARM + CUDA
   própria). É preciso a wheel compilada pra sua versão de JetPack, publicada pela
   NVIDIA no fórum oficial.
2. *ONNX Runtime* — mais leve, não precisa de torch nem torchvision. Exige exportar o
   modelo pra `.onnx` no PC antes de copiar. Costuma ser o caminho mais simples em
   placas antigas, onde a wheel do torch é difícil de achar.

---

## Ajustando o limiar

O padrão é `0.5`, que é o ponto medido no TCC. Subir reduz alarme falso e aumenta gota
perdida — e no portão esses erros têm preços bem diferentes: alarme falso custa banda,
gota perdida some do backend pra sempre.

| limiar | precisão | recall | alarmes falsos | gotas perdidas |
|---|---:|---:|---:|---:|
| 0,25 | 99,25% | 96,11% | 3 | 16 |
| **0,50** | **99,50%** | **96,11%** | **2** | **16** |
| 0,75 | 99,74% | 95,13% | 1 | 20 |
| 0,90 | 100,00% | 92,94% | 0 | 29 |
| 0,99 | 100,00% | 86,62% | 0 | 55 |

Medido sobre as 638 imagens de teste da câmera do projeto (411 com gota, 227 sem).

```python
det = DetectorGota("best_model_tcc.pth", limiar=0.75)
```

Entre 0,25 e 0,75 quase nada muda — o modelo é confiante, quase nenhuma imagem fica em
cima do muro. Mexer no limiar tem retorno pequeno; é mais provável que valha a pena
coletar mais dados do que ajustar essa régua.

---

## O log

Com `log_csv=` no construtor, cada `registrar()` anexa uma linha:

```csv
timestamp,arquivo,classe,probabilidade,limiar,ms
2026-09-11 20:49:08,frame_001.jpg,com_gota,1.000000,0.5,41.2
```

Vale acumular isso em campo: é a evidência de desempenho real, na rua, fora do conjunto
de teste — exatamente o que hoje falta ao trabalho, já que todo o material de treino
vem de uma única sessão de gravação.
