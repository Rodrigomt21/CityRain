# frontend/ — Painel do CityRain

Painel web que mostra, ao vivo, a intensidade de chuva estimada pelas câmeras do carro e pelas câmeras fixas, num mapa com células hexagonais H3.

Produção: https://cityrain.vercel.app

## Telas

| Rota | O que mostra |
|---|---|
| `/` | apresentação do projeto |
| `/dashboard` | ao vivo: classe atual do carro, trajeto dos últimos 30 min, hexágonos das câmeras fixas e dos veículos (seletor Todos / Câmeras fixas / Veículos) |
| `/apresentacao` | modo apresentação em tela cheia para a defesa: mapa, card do carro com chuva animada, pipeline de produção que acende a cada foto, feed e fotos das câmeras fixas |
| `/simulacao` | **simulação ilustrativa** da cidade conectada: frota de carros e câmeras cobrindo São Paulo, chuva por bairro, alerta de chuva forte; nada vai para a API |
| `/historico` | capturas no tempo e no mapa H3 (sem replays de demonstração) |
| `/cameras` · `/cameras/:id` | câmeras fixas com a última foto e série temporal |
| `/dispositivos` | veículos ativos e a última classificação de cada um |

## Stack

React 19, Vite 5, Tailwind CSS 3, React Router 7, Leaflet (react-leaflet) com tiles do OpenStreetMap, h3-js, Recharts (carregado só no histórico) e lucide-react. Testes com Vitest; lint com ESLint.

## Estrutura

```
frontend/src/
├── api/client.js        # GET na API (BASE_URL), erro com status HTTP
├── hooks/               # polling: capturas ao vivo, câmeras, veículos, histórico, série
├── lib/                 # regras puras e testadas: classes e cores, dispositivos e H3, câmeras, apresentação, simulação
├── components/          # dashboard (mapa ao vivo, painéis), layout, landing
└── pages/               # uma por rota
```

As cores e limiares das classes ficam em `src/lib/categories.js` e são os mesmos do modelo (`seco` 0 · `garoa` ≤ 2,5 · `moderada` ≤ 10 · `forte` > 10 mm/h). Captura sem intensidade aparece como "não medido", nunca como seco.

## Rodar

```bash
cd frontend
npm ci
npm run dev                                          # usa a API de produção
VITE_API_URL=http://localhost:8000 npm run dev       # backend local
VITE_POLL_MS=3000 npm run dev                        # atualização mais rápida (demonstração)
```

| Variável | Padrão | Descrição |
|---|---|---|
| `VITE_API_URL` | API de produção no Railway | base da API |
| `VITE_POLL_MS` | 10.000 (ao vivo) | intervalo de atualização |

Nunca coloque chaves em variáveis `VITE_`: elas vão para o JavaScript público. Tudo que o painel lê é público.

## Qualidade

```bash
npx vitest run     # testes das regras puras (src/lib/*.test.js)
npm run lint
npm run build
```

O CI roda lint e build a cada push e PR.

## Deploy

Vercel, a partir desta pasta (`vercel.json` define o build, o fallback do SPA e cabeçalhos de segurança):

```bash
npx vercel deploy --prod --yes
```
