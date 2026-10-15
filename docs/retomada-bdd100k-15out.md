# Retomada: modelo do carro sem sintético + BDD100K (parado em 15/10/2026, 00h10)

## Decisões de 14/10

- **O orientador rejeitou o dado sintético.** O modelo do carro passa a ser treinado sem sintético.
- A CV **v6** (v3 sem sintético) perdeu da v3: F1 irCNN 0,419 × 0,462, diferença pareada
  +0,045 [+0,014; +0,082]. O BDD100K é a tentativa de repor moderada e forte **reais** no
  domínio do para-brisa.
- Dado externo escolhido: só o **BDD100K**, porque é dashcam de celular **atrás do para-brisa**.
  RainSense e nuScenes ficaram de fora (câmera externa, sem para-brisa).
- Rótulo do BDD: **radar NOAA MRMS PrecipRate** (mm/h, a cada 2 min, grade de ~1 km, arquivo do
  IEM desde out/2014). É outra verdade de campo, diferente do pluviômetro, e deve ser declarada no texto.

## Onde está o piloto

Branch `exp/bdd100k-mrms`. Código em `ml/scripts/bdd/`, testes em `ml/tests/test_bdd_mrms.py` (9 passando).
Dados em `ml/data/raw/public_datasets/bdd100k/` (fora do Git). Rodar de dentro de `ml/`.

| Etapa | Script | Estado |
|---|---|---|
| 1. Selecionar imagens `rainy` + amostra `clear` (rótulos do BDD) | `etapa1_selecionar.py` | ✅ 8.821 imagens (rainy: 2.928 dia, 2.495 noite, 384 crepúsculo; clear: 1.009 dia, 1.825 noite) |
| 2. GPS e hora do 10º segundo (só os JSONs necessários, via HTTP Range) | `etapa2_gps.py` | ✅ `selecao_gps.json` |
| 3. Radar MRMS 3×3 em t0, ±2, ±4 min (seco: também ±6, ±10) | `etapa3_mrms.py` | ⏸️ **parcial**: ~16,9 mil janelas em `mrms_janelas.json`; **retoma sozinho** (pula o que já baixou) |
| 4. Rotular pelas faixas + regra de ambiguidade → `ml/data/manifests/bdd_mrms.csv` | `etapa4_rotular.py` | ⏳ não rodou |
| 5. Painéis de 24 miniaturas por classe em `ml/data/review/bdd_mrms/` | `etapa5_paineis.py` | ⏳ não rodou |

Regra de rótulo: classe pelo valor do radar no ponto. Vira **ambíguo** se a vizinhança 3×3 cobre mais
de uma classe ou se ±2 min discordam. **Seco** só com zero na vizinhança e em ±10 min.

## Para retomar (Mac na tomada)

```bash
cd ml
caffeinate -i .venv/bin/python scripts/bdd/etapa3_mrms.py   # ~1–1,5 h restantes
.venv/bin/python scripts/bdd/etapa4_rotular.py
.venv/bin/python scripts/bdd/etapa5_paineis.py
```

Depois: olhar os painéis e a contagem por classe × dia/noite.
- **≥ ~300 moderada+forte inequívocas:** montar a **v7** = carro real + irCNN + BDD (sem sintético) e rodar
  a mesma CV por evento da v3/v6.
- O **seco noturno** do BDD também serve ao **gate**: o alarme falso de noite está em 23–25%.

## Outras pendências do modelo do carro

- **Gate v3** pronto (`ml/runs/gate_v3/gate_v3.onnx`, fora do Git): falta o aceite visual dos painéis
  `ml/data/review/gate_maio_seco/` e a instalação na Jetson (passos em `docs/resultados-experimentos.md` §4.1).
  A Jetson está com o Moreno.
- **Sessões do Moreno:** chegam em 15/10. Processar com `ml/scripts/sessao_carro/processar_sessao.py`
  (guia em `docs/GUIA-SESSAO-CARRO.md`). Viram teste do carro e treino do gate.
- **Mapa ao vivo:** backend novo (#23) mergeado. Falta confirmar o deploy no Railway e ligar o coletor
  das câmeras fixas (`coletor.py ... --enviar --intervalo-s 10`).
