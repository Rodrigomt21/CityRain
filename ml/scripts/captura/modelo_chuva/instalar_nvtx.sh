#!/bin/bash
# Faltava mais uma lib pequena (NVIDIA Tools Extension, 440KB) pro torch importar.
set -e
sudo apt-get install -y cuda-nvtx-10-2

echo ""
echo "Testando import do torch:"
python3 -c "import torch; print('torch', torch.__version__, '| CUDA disponivel:', torch.cuda.is_available())"
