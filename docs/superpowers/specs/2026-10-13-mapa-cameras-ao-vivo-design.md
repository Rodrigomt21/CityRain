# Mapa ao vivo com câmeras fixas e Jetson — design (13/10/2026)

Aprovado pelo Rodrigo em 13/10. Branch: `feat/mapa-cameras-ao-vivo`.

## Objetivo

No mapa ao vivo do dashboard (`/dashboard`), cada câmera — as fixas e a Jetson do carro — aparece
com um **círculo de raio fixo** pintado pela classe da **última foto classificada**, atualizando a
cada **10 s**. Precisa estar de pé (backend + front + coletor) para a demo de 19/10.

## Decisões

- Círculo Leaflet (`Circle`, raio em metros) no `MapaAoVivo.jsx`, raio pela classe (14/10): seco e garoa 1000 m, moderada 600 m, forte 300 m; sem classe ou velha = só o ponto. Chuva forte é localizada; tudo abaixo dos 2 km da rotulagem. Não é célula H3.
- Cor = classe (`lib/categories.js`). **Cinza tracejado** quando a última captura tem mais de
  **2 min** ou `weather_label` nulo ("não medido" nunca vira seco).
- Tooltip: nome, classe, confiança, horário. Fixa mostra miniatura (`imagem_url`). **Jetson nunca
  mostra imagem** (LGPD, regra existente em `camera_service.py`).
- Primeira carga enquadra todas as câmeras com posição + o carro; depois o comportamento atual
  (seguir o carro) continua.
- Polling padrão 10 s em `useLiveCaptures` e `useCameras` (`VITE_POLL_MS` continua sobrescrevendo).
- Modelo da câmera fixa: **provisório** = melhor fold do CV F1 preliminar de 09/10, exportado para
  `backend/app/inference/modelos/intensidade_fixa.onnx`; troca pelo final do Mattioli em 17/10.
- Disco: imagens de câmera fixa ficam só **60 min** (`retencao_imagem_fixa_min` no config);
  linhas de `captures` ficam. Imagem apagada → endpoint já responde 404.
- Coletor: `ml/scripts/coleta_fixa/coletor.py ... --enviar --intervalo-s 10`, no Mac durante a demo.

## Tarefas (executadas por agentes, sem commit; o Rodrigo aprova e faz merge)

- **T1 Front** — círculos, regra de cor/cinza como função pura testada em `lib/cameras.test.js`,
  enquadramento, polling 10 s. `npm test` e `npm run build` passando.
- **T2 Backend** — retenção de imagens de fixa com teste em `backend/tests/`; `pytest` passando.
- **T3 Modelo provisório** — escolher o fold por métrica de validação, exportar com
  `ml/scripts/treino/exportar_onnx_fixa.py`, garantir referências secas que o roteador precisa,
  provar que `RoteadorInferencia` classifica um frame real localmente.
- **T4 Coletor (só leitura)** — medir quanto uma rodada das 11 fontes leva (`--uma-rodada`, sem
  `--enviar`) e listar quais fontes do config não estão cadastradas em produção (GET público).

## Fora do escopo dos agentes (precisa de ok do Rodrigo)

Cadastrar câmeras em produção, deploy no Railway/Vercel, ligar o coletor com `--enviar`.
