#!/bin/bash
# Instala PyTorch (wheel oficial NVIDIA pra JetPack 4.6.1/L4T R32.7, Python 3.6)
# nesta Jetson. Rode com: bash ~/modelo_chuva/instalar_torch.sh
# Vai pedir a senha do sudo uma vez.
set -e

echo "== 1/5: dependencias do sistema =="
sudo apt-get update
sudo apt-get install -y libopenblas-dev

echo "== 2/5: atualizando pip do usuario =="
python3 -m pip install --user --upgrade pip

WHEEL=~/modelo_chuva/torch-1.11.0a0+17540c5+nv22.01-cp36-cp36m-linux_aarch64.whl
if [ ! -f "$WHEEL" ]; then
  echo "== 3/5: baixando wheel do PyTorch (184MB, pode demorar) =="
  curl -L --output "$WHEEL" \
    "https://developer.download.nvidia.com/compute/redist/jp/v461/pytorch/torch-1.11.0a0+17540c5+nv22.01-cp36-cp36m-linux_aarch64.whl"
else
  echo "== 3/5: wheel ja baixado, pulando =="
fi

echo "== 4/5: numpy compativel + Cython =="
python3 -m pip install --user "numpy<1.20" Cython

echo "== 5/5: instalando torch =="
python3 -m pip install --user "$WHEEL"

echo ""
echo "Pronto. Testando import:"
python3 -c "import torch; print('torch', torch.__version__, '| CUDA disponivel:', torch.cuda.is_available())"
