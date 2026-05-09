# frontend/ — Dashboard React

Dashboard web para visualização em tempo real das classificações de chuva agregadas por célula H3 sobre o mapa urbano.

## Stack (definido)

- **React** + **TypeScript**
- Cliente HTTP consumindo o `backend/`
- Biblioteca de mapa **a definir** (candidatos: Mapbox GL, MapLibre, Leaflet, deck.gl)
- **h3-js** para manipular as células no cliente

## Estrutura

```
frontend/
├── public/
└── src/
    ├── components/   # Componentes reutilizáveis (legenda, painel lateral, etc.)
    ├── pages/        # Telas (mapa principal, série temporal, detalhe de célula)
    ├── api/          # Cliente HTTP do backend (fetch / axios)
    ├── hooks/        # React hooks (useRainData, usePolling, etc.)
    └── lib/          # Utilitários — H3, formatação, cores por classe
```

## Categorias visuais

| Classe    | Cor sugerida (placeholder) |
|-----------|----------------------------|
| seco      | cinza claro                |
| garoa     | azul claro                 |
| moderada  | azul                       |
| forte     | azul escuro / roxo         |

## Como rodar (placeholder)

```bash
cd frontend
npm install
npm run dev
```
