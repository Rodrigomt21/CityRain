#!/bin/bash
# libomp5 ja esta instalado, mas so criou libomp.so.5 (versionado).
# O torch pede libomp.so sem versao (nome usado por quem faz link, normalmente
# vem do pacote -dev) -- so falta o symlink.
set -e
sudo ln -sf /usr/lib/aarch64-linux-gnu/libomp.so.5 /usr/lib/aarch64-linux-gnu/libomp.so
sudo ldconfig

echo ""
echo "Testando import do torch:"
python3 -c "import torch; print('torch', torch.__version__, '| CUDA disponivel:', torch.cuda.is_available())"
