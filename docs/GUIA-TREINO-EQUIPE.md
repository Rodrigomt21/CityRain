# Treino do modelo de câmera fixa — guia para a equipe

**Quando:** splits em **13/10**, treinos de 13 a 16/10, teste prospectivo em 18/10. Prazo: 20/10.
**Quem:** quem tiver Mac M-series ou PC com GPU NVIDIA. Em CPU pura cada fold leva horas.

O treino inteiro roda com um script: `ml/scripts/treino/rodar_experimentos_fixa.py`. Ele confere o
ambiente e monta os splits, roda F0 e a validação cruzada de F1, F2 e F3, e aplica o critério de
escolha da spec (CF5). Se o computador dormir ou o processo cair, **rode o mesmo comando de novo**:
ele pula os folds que já terminaram.

Contexto e regras: `docs/specs/spec-camera-fixa.md` (CF4 splits, CF5 modelo) e `docs/PASSAGEM-camera-fixa.md`.

## 1. Preparar a máquina (uma vez, ~15 min + download)

Mac ou Linux/WSL, terminal na raiz `CityRain/`. Precisa de Python 3.11 (`brew install python@3.11` no Mac).

```bash
git pull
python3.11 -m venv ml/.venv
source ml/.venv/bin/activate
python -m pip install -r ml/requirements-treino.txt
```

Com GPU NVIDIA, instale antes o torch do índice CUDA indicado em https://pytorch.org e depois o comando acima.

**Dados** (fora do Git, ~4 GB): baixar `cityrain_dados_treino_fixa_<data>.zip` e o `.sha256` da pasta
compartilhada pelo Rodrigo, conferir e descompactar **na raiz `CityRain/`**:

```bash
shasum -a 256 -c cityrain_dados_treino_fixa_<data>.zip.sha256     # deve dizer OK
unzip -q cityrain_dados_treino_fixa_<data>.zip -d .                # cria ml/data/raw/coleta_fixa, ml/data/processed/ircnn, ...
```

Se outra pessoa fez colheitas depois desse pacote, pegue também a pasta `ml/data/raw/coleta_fixa`
atualizada dela e faça `git pull` (os manifests vão pelo Git).

Conferir:

```bash
python ml/scripts/treino/rodar_experimentos_fixa.py checar
```

Tem de terminar em `[ok] pronto para treinar`. Antes de 13/10 é normal ver os avisos de
"antes do congelamento" e "splits ainda não montados".

## 2. Antes de 13/10: revisão visual (obrigatória)

Moderada e forte rotuladas a 5 km só podem entrar no treino depois de alguém olhar (CF3.2). O script
de splits não tem como saber se alguém olhou, então isso depende da equipe.

1. Gerar os painéis da última colheita (comando no fim do `GUIA-COLETA-EQUIPE.md`) e abrir `ml/data/review/camera_fixa/`.
2. No `revisao.csv`, marcar `excluir=1` + `motivo` **só** em imagem defeituosa: câmera tampada,
   congelada, tela de offline, menu na tela. **Nunca mudar a classe** (quem rotula é o pluviômetro).
3. Ao terminar, criar `ml/data/review/camera_fixa/REVISAO.md` com nome, data, grupos câmera/classe inspecionados e quantas imagens foram marcadas (mesmo registro do `GUIA-COLETA-EQUIPE.md`, seção 6).

## 3. 13/10 em diante: rodar tudo (~5 h em Mac M-series)

```bash
source ml/.venv/bin/activate
python ml/scripts/treino/rodar_experimentos_fixa.py tudo
```

O comando executa, em ordem:

| Etapa | O que faz | Comando avulso |
|---|---|---|
| checar | ambiente, dados, imagens do split | `... checar` |
| splits | `ml/data/splits/fixa_v1.csv`; falha se alguma câmera ficar sem referência seca | `... splits` |
| F0 | modelo do carro (v3) aplicado às câmeras fixas | `... f0` |
| F1, F2, F3 | 4 folds cada (CV por evento do irCNN) + ablação da referência trocada no F3 | `... cv f1 f2 f3` |
| escolher | tabela CF5, comparação pareada com IC95, grava `ml/resultados/fixa_escolha.json` | `... escolher` |

No Mac o script já usa `caffeinate`, mas **deixe o carregador ligado e a tampa aberta**. Se cair, rode
`tudo` de novo e ele continua de onde parou.

**Se o `splits` falhar** com "câmeras sem referência seca", colha seco no DVR daquela câmera e rode de novo:

```bash
python ml/scripts/coleta_fixa/recuperar_dvr.py --modo-seco --fonte <id_da_camera> --passo-s 300
python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa.yaml
```

Se o treino recusar com "evento em train e test_prospectivo", é um evento que cruza o congelamento. **Avise o Rodrigo**, não contorne.

## 4. Conferir a escolha e treinar o modelo final (~30 min)

O `escolher` imprime uma tabela assim:

```
| Exp | F1 irCNN (IC95) | recall forte irCNN | chuva×seco BC | Spearman BC | parâmetros | CF5 |
```

O critério de escolha, fixado na spec antes de olhar os resultados, é:

- maior F1 macro no irCNN;
- recall de forte ≥ 0,7;
- chuva × seco na câmera de teste (BC) ≥ 0,8;
- Spearman > 0;
- em empate estatístico (IC95 da diferença cruza o zero), fica o modelo menor.

Se ninguém passa, o script escolhe pelo F1 e grava `criterio_cf5_atingido: false`, e isso tem de ir para o texto.

1. Colar a tabela em `docs/resultados-experimentos.md`, seção "Câmera fixa", com a linha do F0
   (`ml/resultados/fixa_f0_v3.json`) e, se o F3 estiver na disputa, a linha da referência trocada.
2. Mandar a tabela no grupo. Com o ok, treinar e exportar:

```bash
python ml/scripts/treino/rodar_experimentos_fixa.py final
```

Ele gera `ml/configs/treino_fixa_final.yaml` (épocas = mediana da CV) e treina com todos os eventos.
Depois exporta `backend/app/inference/modelos/intensidade_fixa.onnx` e, se for F3, as referências
em `backend/app/inference/referencias/`. A exportação confere sozinha a paridade PyTorch × ONNX.

3. Commit em branch nova e PR:

```bash
git checkout -b exp/modelo-fixa-final
git add backend/app/inference/modelos/intensidade_fixa.onnx backend/app/inference/referencias \
        ml/configs/treino_fixa_final.yaml ml/resultados docs/resultados-experimentos.md
git commit -m "feat(modelo): modelo de câmera fixa em produção"
git push -u origin exp/modelo-fixa-final
```

Depois do merge, o Moreno faz o deploy e confere `GET /api/v1/cameras/` com `ultima_captura.modelo` preenchido.

## 5. 18/10: teste prospectivo (não retreinar depois)

Depois da última colheita, rodar `splits` de novo e avaliar o modelo final **sem treinar**:

```bash
python ml/scripts/treino/rodar_experimentos_fixa.py splits
python ml/scripts/treino/treinar_fixa.py ml/configs/treino_fixa_final.yaml --avaliar ml/runs/<run fixa_final_...>/melhor.pt
```

Registrar o `test_prospectivo` em `docs/resultados-experimentos.md`. Olhou o prospectivo, não mexe mais no modelo.

## Não fazer

- Mudar limiares, classes, folds ou câmera de teste depois de ver resultado.
- Marcar `posicao_verificada: true` em Santos/Praia Grande sem conferir o endereço da live.
- Commitar `ml/configs/coleta_fixa_tokens.json`, `.env` ou imagens.
- Apagar runs de `ml/runs/`: são a prova dos números do texto.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `checar` diz que falta pacote | `python -m pip install -r ml/requirements-treino.txt` com o venv ativo |
| "imagens do split ausentes" | pacote de dados incompleto ou de outra data; pegar o mais recente |
| fold muito lento (> 1 h) | está em CPU; ver a linha `dispositivo` do `checar` |
| erro de memória na GPU | baixar `treino.batch` na config do experimento (anotar no texto) |
| Windows | usar WSL com Ubuntu; o caminho dos dados tem de estar dentro do WSL |
