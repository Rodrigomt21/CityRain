# Passagem — câmera fixa (09/10 a 20/10/2026)

> O Rodrigo viaja de 09/10 a 12/10. Este guia diz o que cada um faz para o modelo de câmera fixa
> ficar pronto até **20/10**. Spec: `docs/specs/spec-camera-fixa.md`. Plano do modelo:
> `docs/superpowers/plans/2026-10-08-camera-fixa-C-modelo.md` (Task 7).

## Onde estamos (08/10, noite)

- Backend, coletor, rotulagem, splits, treino e dashboard da câmera fixa estão **em produção / na main**
  (PR #17). Página: https://cityrain.vercel.app/cameras
- 6 câmeras cadastradas como `fixa-<id>` e enviando frames: Centro SP, Santos, Praia Grande, Guarujá,
  Ubatuba e Balneário Camboriú. Tokens em `ml/configs/coleta_fixa_tokens.json` (fora do Git — pedir ao
  Rodrigo; nunca commitar).
- Posições conferidas (08/10) de SP, Guarujá, Ubatuba e BC; Santos e Praia Grande ainda aproximadas.
- Colheita de 08/10 feita (ver "Colheitas" no fim). **Falta o modelo fixo treinado** — sem ele as câmeras
  aparecem "Não medido".

## Moreno — backend (fazer já)

1. **Volume no Railway** montado no caminho do `UPLOAD_DIR` (padrão `storage` dentro da app, normalmente
   `/app/storage`). Sem volume as imagens somem a cada deploy.
2. **Gerar uma ADMIN_KEY nova** (a atual apareceu em conversa) e passar ao Rodrigo por canal privado.
3. **Corrigir posição e link no banco** (o cadastro foi feito antes da conferência; não há rota de edição):

```sql
UPDATE devices SET latitude = -23.5393, longitude = -46.6408, descricao = 'Geolan — Rua Vitória (Vitória Hostel), República, SP' WHERE name = 'fixa-sp_centro_geolan';
UPDATE devices SET latitude = -23.9852, longitude = -46.2107, descricao = 'Guarujá — Hotel Palmar, Av. Miguel Estefno 4507, Enseada' WHERE name = 'fixa-guaruja_enseada';
UPDATE devices SET latitude = -23.4653, longitude = -45.0580 WHERE name = 'fixa-ubatuba_tenorio';
UPDATE devices SET stream_url = 'https://www.youtube.com/watch?v=1I0G3d-obsc' WHERE name = 'fixa-santos_gonzaga';
UPDATE devices SET stream_url = 'https://www.youtube.com/watch?v=wNXOI0pmz7I', latitude = -24.0102, longitude = -46.4027 WHERE name = 'fixa-praiagrande_boqueirao';
```

4. Quando o modelo fixo for exportado (passo do ML abaixo), fazer o deploy e conferir que
   `GET /api/v1/cameras/` mostra `ultima_captura.modelo` preenchido.

## Quem tiver um Mac/PC ligado de dia — coletor ao vivo (opcional)

Mantém o dashboard vivo; não é necessário para o treino.

```bash
caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --enviar --intervalo-s 60
```

## Colheita (a cada 2 dias até 18/10 — próxima: **11/10**, depois 13, 15, 17)

O DVR das lives guarda só ~120 h: pular uma colheita perde a chuva daqueles dias.

```bash
ml/.venv/bin/pip install -U yt-dlp
ml/.venv/bin/python ml/scripts/estacoes/baixar_cemaden_ped.py --dias <3 últimos dias, AAAA-MM-DD>
caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --onde-choveu --desde <ISO da última colheita>
caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --modo-seco --passo-s 300 --desde <ISO da última colheita>
ml/.venv/bin/python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa.yaml
ml/.venv/bin/python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa_5km.yaml
ml/.venv/bin/python ml/scripts/dataset/paineis_revisao_fixa.py \
  --manifest ml/data/manifests/manifest_coleta_fixa.csv --manifest ml/data/manifests/manifest_coleta_fixa_5km.csv
```

Depois: abrir `ml/data/review/camera_fixa/`, marcar `excluir=1` + `motivo` no `revisao.csv` **só** para
imagem defeituosa (câmera tampada, congelada, tela de offline). Nunca mudar classe. Commitar os
manifests (`ml/data/manifests/manifest_coleta_fixa*`) e anotar a colheita no fim deste arquivo.

## ML — treino do modelo fixo (13 a 16/10)

> **Atalho (09/10):** os passos abaixo viraram um comando só,
> `python ml/scripts/treino/rodar_experimentos_fixa.py tudo` e depois `... final`. Passo a passo para a
> equipe, com pacote de dados e ambiente: [GUIA-TREINO-EQUIPE.md](GUIA-TREINO-EQUIPE.md). A lista abaixo
> fica como referência do que o script faz.

Pré-requisito: dados (`ml/data/raw/coleta_fixa`, `ml/data/processed/ircnn`) na máquina — zip do Rodrigo.

1. **13/10 — splits** (tudo de 13/10 em diante vira teste prospectivo):
   ```bash
   ml/.venv/bin/python ml/scripts/dataset/montar_splits_fixa.py
   ```
   Conferir no resumo: `referencias_faltando` vazio; cada câmera de treino com `seco` e chuva. Se o treino
   recusar por "evento em train e test_prospectivo", é um evento que cruza o congelamento: avisar.
2. **F0** (referência): `ml/.venv/bin/python ml/scripts/avaliacao/avaliar_v3_em_fixa.py`
3. **F1, F2, F3** — um fold por vez (~20 min cada em Mac M-series; com GPU é mais rápido):
   ```bash
   for k in 0 1 2 3; do caffeinate -i ml/.venv/bin/python ml/scripts/treino/treinar_fixa.py ml/configs/treino_fixa_f1_mnv3.yaml --fold $k; done
   ```
   (repetir com `treino_fixa_f2_effb0.yaml` e `treino_fixa_f3_mnv3_ref.yaml`). Agregar cada um com
   `agregar_cv_fixa` (exemplo no plano C, Task 7, Step 3) e comparar com
   `ml/scripts/avaliacao/comparar_fixa.py`.
4. **Escolha** pelo critério fixado na spec (CF5): maior F1 macro no irCNN com IC; recall de `forte` ≥ 0,7;
   na câmera de teste (BC), acerto chuva×seco ≥ 0,8 e Spearman > 0; empate → modelo menor.
   Para F3, rodar também `--avaliar <ckpt> --referencia-trocada` (prova se a referência ajuda ou só
   identifica a câmera).
5. **Modelo final** (`--fold final`, épocas = mediana da CV, `sem_selecao_por_val: true`) e exportação:
   ```bash
   ml/.venv/bin/python ml/scripts/treino/exportar_onnx_fixa.py ml/runs/<run_final>/melhor.pt
   ```
   Isso grava `backend/app/inference/modelos/intensidade_fixa.onnx` e, se for F3, as referências em
   `backend/app/inference/referencias/`. Commitar os dois juntos e pedir o deploy ao Moreno.
6. **18/10 — teste prospectivo**: última colheita, `montar_splits_fixa.py` de novo, e
   `treinar_fixa.py <config final> --avaliar ml/runs/<run_final>/melhor.pt` (não retreinar depois de olhar).
7. Números para o texto: `docs/resultados-experimentos.md`, seção nova "Câmera fixa".

O que o TCC **não** pode afirmar (revisão final do plano C): nada sobre `seco` no irCNN (quase não sobra
dado); garoa diurna no irCNN; teste em "câmeras novas em geral" (é 1 câmera). O F3 só pode dizer que
"remove o atalho da câmera" com o resultado da referência trocada.

## Paulo — frontend

Nada obrigatório. Pendências pequenas: o eixo de tempo do detalhe da câmera mostra só um rótulo na
janela de 6 h; o mapa ao vivo não enquadra as câmeras fixas quando o carro está parado.

## Demo (19/10)

Roteiro em `docs/roteiro-demo-defesa.md`, seção "Câmera fixa". O replay deve usar a câmera de teste
(`bc_atlantica`) e um evento do mesmo período do dia (dia/noite) da hora da apresentação.

## Colheitas

| Data | Feito por | Janela | Observação |
|---|---|---|---|
| 08/10 | Rodrigo/Claude | DVR desde 05/10 (chuva) e DVR inteiro (seco) | posições corrigidas antes de rotular |
| 09/10 | Rodrigo/Claude | CEMADEN 07–08/10; DVR chuva e seco desde 08/10 20:00Z; seco de Ubatuba | 477 frames novos (SP 91, PG 231, BC 148, Ubatuba 7); leituras só até 08/10 23:50Z → **próxima colheita com `--desde 2026-10-09T00:10:00Z`** e CEMADEN de 09/10 em diante |

## Continuação local — 08/10, 23h

Coleta e manifests atualizados: 166 frames novos, acervo de 18.577 pares. Painéis de revisão gerados; revisão humana pendente. CEMADEN parcialmente atualizado, com limite de acesso ao completar 08/10. Detalhes e próximos passos em [coleta-2026-10-08-continuacao.md](coleta-2026-10-08-continuacao.md). Nenhum coletor contínuo ou agendamento ficou ativo.

**Atualização posterior (08/10, 23:22):** Rodrigo pediu e foi ativada coleta contínua local das seis câmeras, a cada 10 minutos, sem envio ao backend. Ver log e detalhes no relatório acima.

## 09/10 — pronto para a equipe treinar

- `ml/requirements-treino.txt` (torch, torchvision, onnx, onnxruntime) e `ml/scripts/treino/rodar_experimentos_fixa.py` (checar → splits → F0 → CV F1/F2/F3 → escolha CF5 → final + ONNX, retomável).
- Ubatuba não tinha `seco` de referência: com `exigir_referencia`, todas as linhas dela (inclusive as únicas `forte` de treino) saíam dos modelos. Colhido seco no DVR (`--modo-seco --fonte ubatuba_tenorio`, 59 frames) e manifests regenerados: `referencias_faltando` vazio.
- Pacote de dados para a equipe: `cityrain_dados_treino_fixa_20261009.zip` + `.sha256` (coleta_fixa, irCNN processado, estações, painéis de revisão).
- Coletor contínuo do Mac do Rodrigo parou em 09/10 02:33 UTC (Mac dormiu). A colheita de 11/10 pelo DVR cobre o intervalo.
