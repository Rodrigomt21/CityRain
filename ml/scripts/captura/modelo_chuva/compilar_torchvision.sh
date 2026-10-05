#!/bin/bash
# Compila o torchvision 0.12.0 do zero (nao tem wheel pronta pra essa combinacao
# JetPack 4.6 + torch 1.11 + Python 3.6). Vai demorar bastante na Nano
# (pode levar 40-90min). Rode com: bash ~/modelo_chuva/compilar_torchvision.sh
#
# MAX_JOBS=2 (nao usa os 4 nucleos) pra nao estourar a RAM (so ~650MB livres
# + 2GB reclamavel + swap). Se travar/OOM, editar esse arquivo e trocar
# MAX_JOBS=2 por MAX_JOBS=1 antes de rodar de novo.
set -e

echo "== 1/4: dependencias do sistema =="
sudo apt-get install -y libjpeg-dev zlib1g-dev libpython3-dev \
    libavcodec-dev libavformat-dev libswscale-dev

echo "== 2/4: Pillow (o torchvision precisa) =="
python3 -m pip install --user "pillow"

echo "== 3/4: clonando codigo-fonte do torchvision (v0.12.0, par certo do torch 1.11) =="
cd ~/modelo_chuva
if [ ! -d torchvision ]; then
  git clone --branch v0.12.0 --depth 1 https://github.com/pytorch/vision torchvision
fi

echo "== 4/4: compilando (isso demora, pode ir fazer outra coisa) =="
cd ~/modelo_chuva/torchvision
export BUILD_VERSION=0.12.0
export MAX_JOBS=2
python3 setup.py install --user

echo ""
echo "Testando import:"
python3 -c "
import torch, torchvision
from torchvision.models import mobilenet_v2
print('torch', torch.__version__)
print('torchvision', torchvision.__version__)
print('mobilenet_v2 ok')
"
