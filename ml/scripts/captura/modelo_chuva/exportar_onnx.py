"""
exportar_onnx.py — Converte bestModel.pth (MobileNetV2 vendorizado) pra ONNX,
uma vez só, offline. Não precisa rodar de novo a cada boot.

Uso: python3 exportar_onnx.py [--modelo bestModel.pth] [--saida bestModel.onnx]
"""
import argparse
import inspect

import torch
import torch.nn as nn

from mobilenetv2_vendored import mobilenet_v2

RESOLUCAO = 384


def carrega_modelo(caminho_pth):
    aceita_weights = "weights" in inspect.signature(mobilenet_v2).parameters
    modelo = mobilenet_v2(weights=None) if aceita_weights else mobilenet_v2(pretrained=False)
    modelo.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(modelo.last_channel, 2))
    estado = torch.load(caminho_pth, map_location="cpu")
    if isinstance(estado, dict) and "state_dict" in estado:
        estado = estado["state_dict"]
    modelo.load_state_dict(estado)
    return modelo.eval()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="bestModel.pth")
    ap.add_argument("--saida", default="bestModel.onnx")
    args = ap.parse_args()

    modelo = carrega_modelo(args.modelo)
    entrada_fake = torch.zeros(1, 3, RESOLUCAO, RESOLUCAO, dtype=torch.float32)

    torch.onnx.export(
        modelo,
        entrada_fake,
        args.saida,
        input_names=["input"],
        output_names=["output"],
        opset_version=11,
        dynamic_axes=None,  # tamanho de batch/entrada fixos: mais simples pro TensorRT otimizar
    )
    print(f"exportado: {args.saida}")


if __name__ == "__main__":
    main()
