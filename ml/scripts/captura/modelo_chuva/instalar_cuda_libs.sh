#!/bin/bash
# O torch já instalou, mas falha ao importar (falta libcurand.so.10 e outras
# libs CUDA que o wheel da NVIDIA espera encontrar no sistema, mesmo rodando
# só em CPU). Instala as libs de runtime que faltam (~1,8GB, cabe no disco).
# Rode com: bash ~/modelo_chuva/instalar_cuda_libs.sh
set -e

sudo apt-get install -y cuda-libraries-10-2 libcudnn8

echo ""
echo "Testando import do torch:"
python3 -c "import torch; print('torch', torch.__version__, '| CUDA disponivel:', torch.cuda.is_available())"
