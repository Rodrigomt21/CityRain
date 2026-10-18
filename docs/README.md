# docs/ — Documentação do CityRain

## Comece por aqui

| Documento | Para quê |
|---|---|
| [`resultados-experimentos.md`](resultados-experimentos.md) | protocolo, todos os experimentos e números que sustentam o capítulo de resultados |
| [`roteiro-demo-defesa.md`](roteiro-demo-defesa.md) | como montar e conduzir a demonstração ao vivo na defesa |
| [`CODEBASE_MAP.md`](CODEBASE_MAP.md) | mapa do código: onde fica cada parte e como elas conversam |
| [`acervo-dados.md`](acervo-dados.md) | inventário de todas as fontes de dados e o que cada uma rendeu |

## Guias de operação

| Documento | Para quê |
|---|---|
| [`GUIA-SESSAO-CARRO.md`](GUIA-SESSAO-CARRO.md) | sair com o carro e transformar a sessão da Jetson em frames rotulados |
| [`GUIA-COLETA-EQUIPE.md`](GUIA-COLETA-EQUIPE.md) | coletar as câmeras fixas, colher o DVR das lives e revisar |
| [`GUIA-TREINO-EQUIPE.md`](GUIA-TREINO-EQUIPE.md) | treinar, escolher e trocar o modelo da câmera fixa |
| [`protocolo-piloto-chuva-simulada.md`](protocolo-piloto-chuva-simulada.md) | piloto de chuva simulada no para-brisa com intensidade medida |

## Especificações (`specs/`)

| Documento | Tema |
|---|---|
| [`spec-pipeline-jetson.md`](specs/spec-pipeline-jetson.md) | captura, gate e envio na Jetson |
| [`integracao-jetson-backend-frontend.md`](specs/integracao-jetson-backend-frontend.md) | contrato entre Jetson, API e painel |
| [`spec-camera-fixa.md`](specs/spec-camera-fixa.md) | modelo da câmera fixa: splits, congelamento e critério de escolha |
| [`spec-dataset-balanceado.md`](specs/spec-dataset-balanceado.md) | montagem do dataset do modelo de intensidade |
| [`spec-normalizacao-orientacao.md`](specs/spec-normalizacao-orientacao.md) | orientação das imagens por sessão |
| [`spec-historico-estacoes.md`](specs/spec-historico-estacoes.md) | histórico das estações pluviométricas |

## Histórico e registros

Documentos datados que registram decisões e passagens de bastão. Valem como histórico; o estado atual está no `README.md` da raiz e em `resultados-experimentos.md`.

- [`PASSAGEM-camera-fixa.md`](PASSAGEM-camera-fixa.md): divisão de tarefas da câmera fixa (09–20/10/2026)
- [`COMO-CONTINUAR.md`](COMO-CONTINUAR.md): estado do modelo do carro em 07/10/2026
- [`plano-dataset.md`](plano-dataset.md), [`fontes-estacoes.md`](fontes-estacoes.md), [`coleta-2026-10-08-continuacao.md`](coleta-2026-10-08-continuacao.md)
- `mensagem-*.txt`: mensagens enviadas ao grupo
- `superpowers/`: planos e specs de implementação usados durante o desenvolvimento

## Convenções

- Datas em formato ISO (AAAA-MM-DD) nos nomes de arquivo; no texto, DD/MM/AAAA.
- Números sempre com a fonte (config, run ou arquivo em `ml/resultados/`).
- Documento final do TCC em formato ABNT, fora deste repositório.
