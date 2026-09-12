"""
Diagnostico do detector na Jetson - para rodar ANTES de colocar em producao.

Envolve o detector.py por fora, sem alterar nada dentro dele: o detector ja foi
validado como bit a bit identico ao pipeline de treino, e mexer nele invalidaria
essa prova. Aqui so olhamos o que entra, o que sai, e o que o modelo enxerga.

Para cada imagem, salva em debug/<nome>/:
    1_recebida.png    a imagem exatamente como chegou
    2_preparada.png   o que o MODELO enxerga (384x384, desnormalizada de volta)
    3_painel.png      as duas lado a lado com todos os numeros

E anexa uma linha em debug/diagnostico.csv.

Uso:
    python3 diagnostico.py foto.jpg
    python3 diagnostico.py --pasta fotos_da_jetson/
    python3 diagnostico.py foto.jpg --limiar 0.75 --cpu

O que procurar no resultado
---------------------------
A imagem "preparada" e a prova visual mais importante: se ela estiver com as
cores trocadas, de cabeca para baixo, esticada ou escura demais, o modelo esta
vendo outra coisa - e nenhum numero de acuracia do TCC vale mais.
"""
import argparse
import csv
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detector as det_mod
from detector import DetectorGota, MEDIA, DESVIO, RESOLUCAO

# O dataset de treino e 640x480 (4:3). Se a camera da Jetson entregar outro
# formato, o "esmagamento" para o quadrado 384x384 sera diferente do que a rede
# viu no treino - e isso desloca o dominio sem dar erro nenhum.
ASPECTO_TREINO = 640.0 / 480.0
COLUNAS = ["timestamp", "arquivo", "largura", "altura", "aspecto", "brilho",
           "media_r", "media_g", "media_b", "classe", "probabilidade",
           "prob_girada_180", "ms", "avisos"]


def _fonte(tam):
    for nome in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(nome, tam)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def desnormalizar(x):
    """Converte o tensor de volta para imagem visivel.

    E o passo que revela o que o modelo realmente recebeu - depois do RGB, do
    redimensionamento e da normalizacao. Se esta figura estiver errada, o
    problema esta no preparo, nao no modelo."""
    arr = x[0].transpose(1, 2, 0)          # CHW -> HWC
    arr = arr * DESVIO + MEDIA             # desfaz a normalizacao
    arr = np.clip(arr, 0.0, 1.0) * 255.0
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def carregar_como_pil(caminho):
    """Le a imagem do disco do mesmo jeito que o detector le."""
    return Image.open(caminho).convert("RGB")


def analisar(img_pil, x_tensor):
    """Estatisticas da imagem recebida e do tensor que vai para a rede."""
    arr = np.asarray(img_pil, dtype=np.float32)
    larg, alt = img_pil.size
    info = {
        "largura": larg,
        "altura": alt,
        "aspecto": larg / float(alt) if alt else 0.0,
        "brilho": float(arr.mean()),
        "desvio": float(arr.std()),
        "media_r": float(arr[:, :, 0].mean()),
        "media_g": float(arr[:, :, 1].mean()),
        "media_b": float(arr[:, :, 2].mean()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "tensor_media": [float(x_tensor[0, c].mean()) for c in range(3)],
        "tensor_desvio": [float(x_tensor[0, c].std()) for c in range(3)],
    }
    return info


def avisos_de(info, prob, limiar, prob_180):
    """Checagens automaticas: o que costuma dar errado em deploy de camera."""
    avisos = []

    dif = abs(info["aspecto"] - ASPECTO_TREINO) / ASPECTO_TREINO
    if dif > 0.08:
        avisos.append(
            "aspecto {:.2f} difere do treino ({:.2f}): a imagem sera esmagada "
            "de forma diferente da que a rede viu".format(
                info["aspecto"], ASPECTO_TREINO))

    if info["largura"] < RESOLUCAO or info["altura"] < RESOLUCAO:
        avisos.append("resolucao menor que {0}x{0}: a imagem sera ampliada, "
                      "perdendo o detalhe fino da gota".format(RESOLUCAO))

    if info["brilho"] < 18:
        avisos.append("imagem muito escura (brilho {:.0f}/255): conferir "
                      "exposicao da camera".format(info["brilho"]))
    elif info["brilho"] > 225:
        avisos.append("imagem muito clara (brilho {:.0f}/255): possivel "
                      "superexposicao".format(info["brilho"]))

    if info["desvio"] < 8:
        avisos.append("imagem quase uniforme (desvio {:.1f}): lente tampada, "
                      "frame vazio ou captura falhando?".format(info["desvio"]))

    if abs(prob - limiar) < 0.15:
        avisos.append("decisao em cima do limiar (prob {:.1f}%, limiar {:.0f}%): "
                      "caso duvidoso".format(100 * prob, 100 * limiar))

    if prob_180 is not None and prob_180 - prob > 0.35:
        avisos.append("girada 180 graus a confianca sobe de {:.1f}% para {:.1f}%: "
                      "a camera pode estar montada de cabeca para baixo".format(
                          100 * prob, 100 * prob_180))

    return avisos


def montar_painel(recebida, preparada, info, r, prob_180, avisos, destino):
    """Figura unica com as duas imagens e todos os numeros - o artefato que
    voce olha para decidir se pode ou nao fazer o deploy."""
    alvo_h = 420
    esc = alvo_h / float(recebida.height)
    rec = recebida.resize((int(recebida.width * esc), alvo_h), Image.BILINEAR)
    pre = preparada.resize((alvo_h, alvo_h), Image.NEAREST)

    pad, topo, texto_h = 16, 34, 250
    larg = pad * 3 + rec.width + pre.width
    tela = Image.new("RGB", (larg, topo + alvo_h + texto_h), (17, 21, 24))
    d = ImageDraw.Draw(tela)
    f_tit = _fonte(16)
    f_txt = _fonte(14)
    f_peq = _fonte(13)

    cinza, branco = (150, 162, 168), (232, 238, 240)
    verde, amarelo, vermelho = (95, 190, 140), (215, 175, 70), (220, 95, 80)

    d.text((pad, 9), "1. RECEBIDA  {}x{}".format(info["largura"], info["altura"]),
           font=f_tit, fill=cinza)
    d.text((pad * 2 + rec.width, 9),
           "2. O QUE O MODELO VE  {0}x{0}".format(RESOLUCAO), font=f_tit, fill=cinza)
    tela.paste(rec, (pad, topo))
    tela.paste(pre, (pad * 2 + rec.width, topo))

    y = topo + alvo_h + 14
    cor_classe = verde if r["tem_gota"] else cinza
    d.text((pad, y), "{}   {:.2f}%".format(r["classe"].upper().replace("_", " "),
                                           100 * r["probabilidade"]),
           font=_fonte(24), fill=cor_classe)
    d.text((pad + 260, y + 7), "limiar {:.0f}%   {:.0f} ms".format(
        100 * r["limiar"], r["ms"]), font=f_txt, fill=cinza)

    y += 38
    linhas = [
        "aspecto      {:.3f}   (treino 1.333)".format(info["aspecto"]),
        "brilho       {:.1f} / 255     desvio {:.1f}".format(info["brilho"], info["desvio"]),
        "faixa        {:.0f} a {:.0f}".format(info["min"], info["max"]),
        "media R/G/B  {:.1f} / {:.1f} / {:.1f}".format(
            info["media_r"], info["media_g"], info["media_b"]),
        "tensor media {:+.2f} {:+.2f} {:+.2f}   desvio {:.2f} {:.2f} {:.2f}".format(
            info["tensor_media"][0], info["tensor_media"][1], info["tensor_media"][2],
            info["tensor_desvio"][0], info["tensor_desvio"][1], info["tensor_desvio"][2]),
    ]
    if prob_180 is not None:
        linhas.append("girada 180   {:.2f}%".format(100 * prob_180))
    for ln in linhas:
        d.text((pad, y), ln, font=f_peq, fill=branco)
        y += 19

    y += 6
    if avisos:
        d.text((pad, y), "AVISOS", font=f_txt, fill=amarelo)
        y += 20
        for a in avisos:
            cor = vermelho if ("cabeca para baixo" in a or "uniforme" in a) else amarelo
            for i, pedaco in enumerate(_quebrar(a, 110)):
                prefixo = "- " if i == 0 else "  "
                d.text((pad + 10, y), prefixo + pedaco, font=f_peq, fill=cor)
                y += 17
    else:
        d.text((pad, y), "nenhum aviso - entrada compativel com o treino",
               font=f_txt, fill=verde)

    tela.save(destino)
    return destino


def _quebrar(texto, largura):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = (atual + " " + p).strip()
    if atual:
        linhas.append(atual)
    return linhas


def diagnosticar(det, caminho, pasta_debug, girar=True):
    nome = os.path.splitext(os.path.basename(caminho))[0]
    saida = os.path.join(pasta_debug, nome)
    if not os.path.isdir(saida):
        os.makedirs(saida)

    recebida = carregar_como_pil(caminho)
    x = det_mod.preparar(caminho)
    preparada = desnormalizar(x)

    t0 = time.time()
    r = det.prever(caminho)
    r["ms"] = (time.time() - t0) * 1000.0

    prob_180 = None
    if girar:
        girada = recebida.rotate(180)
        prob_180 = float(det.motor.inferir(det_mod.preparar(girada))[1])

    info = analisar(recebida, x)
    avisos = avisos_de(info, r["probabilidade"], r["limiar"], prob_180)

    recebida.save(os.path.join(saida, "1_recebida.png"))
    preparada.save(os.path.join(saida, "2_preparada.png"))
    painel = montar_painel(recebida, preparada, info, r, prob_180, avisos,
                           os.path.join(saida, "3_painel.png"))

    # --- console ---
    print("\n" + "=" * 72)
    print(os.path.basename(caminho))
    print("=" * 72)
    print("  recebida     {}x{}  aspecto {:.3f} (treino 1.333)".format(
        info["largura"], info["altura"], info["aspecto"]))
    print("  brilho       {:.1f}/255   desvio {:.1f}   faixa {:.0f}-{:.0f}".format(
        info["brilho"], info["desvio"], info["min"], info["max"]))
    print("  media R/G/B  {:.1f} / {:.1f} / {:.1f}".format(
        info["media_r"], info["media_g"], info["media_b"]))
    print("  tensor       media {} desvio {}".format(
        " ".join("{:+.2f}".format(v) for v in info["tensor_media"]),
        " ".join("{:.2f}".format(v) for v in info["tensor_desvio"])))
    print("  VEREDITO     {}  {:.2f}%   ({:.0f} ms, motor {})".format(
        r["classe"], 100 * r["probabilidade"], r["ms"], det.motor.nome))
    if prob_180 is not None:
        print("  girada 180   {:.2f}%".format(100 * prob_180))
    if avisos:
        print("  AVISOS:")
        for a in avisos:
            print("    - " + a)
    else:
        print("  sem avisos: entrada compativel com o treino")
    print("  figuras      {}".format(saida))

    linha = [time.strftime("%Y-%m-%d %H:%M:%S"), os.path.basename(caminho),
             info["largura"], info["altura"], "{:.4f}".format(info["aspecto"]),
             "{:.1f}".format(info["brilho"]), "{:.1f}".format(info["media_r"]),
             "{:.1f}".format(info["media_g"]), "{:.1f}".format(info["media_b"]),
             r["classe"], "{:.6f}".format(r["probabilidade"]),
             "" if prob_180 is None else "{:.6f}".format(prob_180),
             "{:.1f}".format(r["ms"]), " | ".join(avisos)]
    return linha, painel


def main():
    ap = argparse.ArgumentParser(description="Diagnostico do detector antes do deploy")
    ap.add_argument("imagem", nargs="?", help="uma imagem")
    ap.add_argument("--pasta", help="diagnostica todas as imagens de uma pasta")
    ap.add_argument("--modelo", default="best_model_tcc.pth")
    ap.add_argument("--limiar", type=float, default=det_mod.LIMIAR_PADRAO)
    ap.add_argument("--saida", default="debug", help="pasta de saida (padrao: debug/)")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--sem-giro", action="store_true",
                    help="nao testar a imagem girada 180 graus")
    args = ap.parse_args()

    if not args.imagem and not args.pasta:
        ap.error("informe uma imagem ou --pasta")

    alvos = []
    if args.pasta:
        ext = (".jpg", ".jpeg", ".png", ".bmp")
        for n in sorted(os.listdir(args.pasta)):
            if n.lower().endswith(ext):
                alvos.append(os.path.join(args.pasta, n))
    if args.imagem:
        alvos.append(args.imagem)
    if not alvos:
        raise SystemExit("nenhuma imagem encontrada")

    if not os.path.isdir(args.saida):
        os.makedirs(args.saida)

    det = DetectorGota(args.modelo, limiar=args.limiar, usar_gpu=not args.cpu)
    print("motor: {}   modelo: {}   limiar: {:.2f}".format(
        det.motor.nome, args.modelo, args.limiar))

    linhas = []
    for caminho in alvos:
        linha, _ = diagnosticar(det, caminho, args.saida, girar=not args.sem_giro)
        linhas.append(linha)

    csv_path = os.path.join(args.saida, "diagnostico.csv")
    novo = not os.path.isfile(csv_path)
    with open(csv_path, "a", newline="") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(COLUNAS)
        w.writerows(linhas)

    com_aviso = sum(1 for l in linhas if l[-1])
    print("\n" + "=" * 72)
    print("{} imagens | {} com aviso | planilha: {}".format(
        len(linhas), com_aviso, csv_path))
    print("=" * 72)


if __name__ == "__main__":
    main()
