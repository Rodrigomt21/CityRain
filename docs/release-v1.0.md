# CityRain v1.0

Versão apresentada na defesa do TCC (Instituto Mauá de Tecnologia, outubro de 2026).

O CityRain estima a intensidade da chuva a partir de câmeras que já existem: no para-brisa de carros e em lives públicas. Cada foto vira uma classe (`seco`, `garoa`, `moderada` ou `forte`) com posição e horário, agregada em hexágonos H3 de ~460 m e mostrada ao vivo num painel web. Em produção o modelo vê só a imagem; pluviômetros (CEMADEN) e radar (NOAA MRMS) servem apenas para rotular o treino e avaliar.

- **Painel:** https://cityrain.vercel.app (modo apresentação em `/apresentacao`)
- **API (OpenAPI):** https://api-production-046f.up.railway.app/docs

## Modelos anexados

| Arquivo | Papel | Versão | Entrada | Classes | Tamanho | SHA-256 |
|---|---|---|---|---|---|---|
| `intensidade.onnx` | intensidade no carro (backend) | v14f (`intensidade_final_v14f_limpo_dia_mnv3_foldfinal`, época 6) | 3×288×384 | garoa, moderada, forte | 16,8 MB | `5abd9189…2b21e546` |
| `intensidade_fixa.onnx` | intensidade na câmera fixa (backend) | `fixa_f1_mnv3_fold0`, época 2 | 3×288×384 | seco, garoa, moderada, forte | 16,8 MB | `e48d2ff3…c9948346` |
| `gate_v4.onnx` | gate chuva × seco na Jetson Nano | gate v4 (MobileNetV2, opset 11) | 3×384×384 | seco, com gota | 8,9 MB | `b38f7aef…b6d65879` |

Os dois modelos de intensidade são MobileNetV3-Large treinados em PyTorch e trazem no próprio arquivo as classes, o tamanho de entrada e a normalização, que o backend lê ao carregar. O gate devolve dois logits (índice 1 = com gota); a Jetson aplica limiar 0,5 (`limiar_chuva` no `cityrain_config.json`).

## Principais resultados

Todos em dados nunca vistos no treino. Detalhes, protocolo e intervalos em [`docs/resultados-experimentos.md`](resultados-experimentos.md).

**Modelo do carro (v14f), sem dado sintético, só de dia:**

| Teste | v7 (anterior) | v14f |
|---|---|---|
| Para-brisa em dias, câmeras e cidades nunca vistos (F1 macro) | 0,167 | 0,457 |
| Temporal de SP 10/03/2023 (CEMADEN 35–87 mm/h): frames forte | 0% | 13% |
| Temporal de SP: frames moderada ou mais | 64% | 59% |
| Vídeos de temporal: pico classificado acima do início | 0,705 | 0,931 |
| Garoa do nosso carro em sessão nunca vista | 100% | 98,7% |

No mesmo teste de para-brisa, responder sempre a classe majoritária dá F1 macro 0,170 e sortear na proporção das classes dá 0,333.

**Gate v4 (sessão nunca vista, limiar 0,5):** alarme falso no seco de dia de 1–13% (gate v3: 33–41%) e recall de chuva de 0,88–0,98; no seco noturno o alarme falso fica em 0,23–0,34.

**Borda (Jetson Nano, CUDA):** gate 11 FPS e intensidade 14 FPS, contra captura a 1 fps.

**Câmera fixa:** câmera nunca vista (Balneário Camboriú) com 69% de acerto e 98% em chuva × seco; recall de forte 0,72 no irCNN.

## Limitações conhecidas

- No para-brisa, a generalização para dias e câmeras nunca vistos ainda é limitada; a moderada é a classe mais difícil (24% de acerto).
- O forte de para-brisa rotulado vem dos EUA (radar MRMS); em SP o teste de temporal não tem hora exata por frame.
- O modelo do carro é só de dia; o gate erra mais à noite.
- O modelo da câmera fixa tem poucos exemplos de seco e marca parte das fotos secas como garoa.
