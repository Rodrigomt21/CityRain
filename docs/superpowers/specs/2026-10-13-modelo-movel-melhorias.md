# Modelo móvel — melhorias até 20/10 (13/10/2026)

Dono: Rodrigo. Mattioli cuida do modelo fixo. Moreno está com a Jetson esta semana.

## M1 — Gate da Jetson (chuva | seco)
Hoje passa só 10% (13/09) e 36% (23/09) da chuva real.
1. Curva do limiar do gate de produção: recall de chuva (01/09, 13/09, 23/09) × falso alarme
   (seco 04/08 dia, 06/08 noite) para limiares 0,05–0,5. Recomendar limiar.
2. Gate v2 com validação por sessão (nunca testar em sessão vista no treino), usando também
   dado externo de para-brisa (`ml/data/raw/public_datasets/raindrops_zenodo/`) se servir.
   Aceite: recall de chuva maior que o original em sessão não vista com falso alarme ≤ original.

## M2 — Intensidade no backend (garoa | moderada | forte)
CV v6 = v3 **sem sintético** (`origens_treino: [real]` + irCNN), mesmo protocolo, comparado
com v3 por IC por evento (`intervalos_confianca.py`). Se empatar, sintético sai (resposta ao
orientador). Resultado em `docs/resultados-experimentos.md`.

## M3 — Sessões novas do carro
Um comando que pega uma sessão da Jetson, baixa CEMADEN dos dias, gera rótulos
(`gerar_manifest`) e imprime o resumo por classe — para as saídas do Moreno virarem teste.

Regras: sintético nunca em teste; rótulo só de pluviômetro; nada de deploy/merge sem o Rodrigo.
