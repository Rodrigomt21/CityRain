# Câmera fixa — Plano D: Dashboard e demonstração

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O dashboard mostra as câmeras fixas ao vivo (página "Câmeras", detalhe com série, ícone próprio no mapa) sem misturar com o trajeto do carro, e existe um replay de chuva real pelas câmeras para a defesa.

**Architecture:** Lógica de apresentação em funções puras (`src/lib/cameras.js`), testadas com Vitest; hooks finos sobre a API do Plano A (`GET /api/v1/cameras/`, `/cameras/{id}/serie`, `/captures/{id}/imagem`, `?tipo=`). O replay é um script Python que reenvia frames de um evento real ao `/ingest` com `metadata.demo`, alterando só o segmento de comentário do JPEG para não cair na deduplicação por hash.

**Tech Stack:** React 19 + Vite 5 + react-router-dom 7 + react-leaflet 5 + recharts 3 + Tailwind (JSX, sem TypeScript); Vitest (novo, só para funções puras); Python 3.11+ para o replay.

**Spec:** `docs/specs/spec-camera-fixa.md` (seções CF7 e CF8). Consome a API do Plano A (Task 6) e as funções `metadados_ingest`, `enviar_frame`, `token_da_fonte` do Plano B (Task 1).

## Global Constraints

- Todo número exibido vem da API; nada fixo no código.
- Rótulo nulo aparece como **"Não medido"** (`categoryFromLabel` já faz isso), nunca como "Seco".
- Sem dois eixos y em gráfico nenhum; séries diferentes ficam em gráficos empilhados.
- Câmeras fixas **nunca** entram no trajeto do carro (`MapaAoVivo` e `useLiveCaptures` usam `tipo=movel`).
- Imagens vêm de `BASE_URL + imagem_url`; se a imagem falhar (404 no Railway sem volume), mostrar um bloco "imagem indisponível", sem quebrar a página.
- Frontend: `npm run lint` e `npm run build` sem erro em `frontend/`. Código em JSX, estilo das páginas existentes (CSS variables `--bg-*`, `--text-*`, `font-mono` nos números).
- Frontend é do Paulo: o PR deste plano vai para revisão dele antes do merge.
- Commits `tipo: descrição` em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Sem push.

## Review Focus

1. **Câmeras fixas mandando frames a cada minuto** → o trajeto do carro no Dashboard continua só com o carro (Task 3).
2. **Imagem da última captura indisponível** → card mostra "imagem indisponível" e o resto (classe, horário) continua (Task 2).
3. **Câmera sem nenhuma captura ainda** → card com "sem captura ainda", sem `NaN` nem "há NaN min" (Task 1).
4. **API fora do ar** → página "Câmeras" mostra a mensagem de erro e tenta de novo no próximo ciclo (Task 2).
5. **Replay rodado duas vezes no mesmo dia** → as capturas entram de novo (hash diferente), marcadas como demo, e o histórico continua excluindo demo (Task 5).

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `frontend/package.json`, `frontend/vite.config.js` | modificar | Vitest (`npm test`) |
| `frontend/src/lib/cameras.js` | criar | funções puras de apresentação das câmeras |
| `frontend/src/lib/cameras.test.js` | criar | testes |
| `frontend/src/hooks/useCameras.js`, `useSerieCamera.js` | criar | dados da API |
| `frontend/src/pages/Cameras.jsx`, `CameraDetalhe.jsx` | criar | páginas |
| `frontend/src/components/cameras/CameraCard.jsx` | criar | card da grade |
| `frontend/src/App.jsx`, `frontend/src/pages/Dashboard.jsx` | modificar | rotas e links |
| `frontend/src/hooks/useLiveCaptures.js` | modificar | `tipo=movel` |
| `frontend/src/components/dashboard/MapaAoVivo.jsx` | modificar | camada de câmeras fixas (quadrado) |
| `frontend/src/hooks/useHistorico.js`, `frontend/src/pages/Historico.jsx` | modificar | filtro Todas/Fixas/Móveis |
| `.github/workflows/ci.yml` | modificar | `npm test` no job do frontend |
| `ml/scripts/coleta_fixa/replay_evento.py` | criar | replay de chuva real pelas câmeras |
| `ml/tests/test_replay_evento.py` | criar | testes do replay |
| `docs/roteiro-demo-defesa.md` | modificar | seção "Câmera fixa" |

---

### Task 1: Vitest e funções puras das câmeras

**Files:**
- Modify: `frontend/package.json`, `frontend/vite.config.js`, `.github/workflows/ci.yml`
- Create: `frontend/src/lib/cameras.js`, `frontend/src/lib/cameras.test.js`

**Interfaces:**
- Produces (`src/lib/cameras.js`):
  - `MINUTOS_AO_VIVO = 15`.
  - `haQuanto(iso: string | null, agora: Date = new Date()) -> string` — `"sem captura ainda"` (nulo), `"agora mesmo"` (< 1 min), `"há N min"`, `"há N h"`, `"há N d"`.
  - `aoVivo(iso, agora) -> boolean` — última captura há ≤ 15 min.
  - `resumoCamera(cam: CameraResumo, baseUrl: string, agora: Date = new Date()) -> { id, nome, descricao, categoria, confiancaPct: number | null, quando: string, aoVivo: boolean, imagemSrc: string | null, modelo: string | null }`. `nome` = `descricao` ou `name` sem o prefixo `fixa-`.
  - `pontosSerie(serie: PontoSerie[]) -> { t: number, nivel: number | null, cor: string, rotulo: string }[]` — `nivel` 0..3 para seco..forte, `null` para não medido.
- Formato de `CameraResumo` e `PontoSerie`: Plano A Task 6.

- [ ] **Step 1: Instalar o Vitest**

```bash
cd frontend && npm install -D vitest@^2.1.0
```

Em `package.json`, `"scripts"`: `"test": "vitest run"`. Em `vite.config.js`:

```js
export default defineConfig({
  plugins: [react()],
  test: { environment: 'node', include: ['src/**/*.test.js'] },
})
```

- [ ] **Step 2: Testes que falham** (`frontend/src/lib/cameras.test.js`)

```js
import { describe, expect, it } from 'vitest'
import { aoVivo, haQuanto, pontosSerie, resumoCamera } from './cameras'

const AGORA = new Date('2026-10-09T18:00:00Z')
const iso = (minAtras) => new Date(AGORA.getTime() - minAtras * 60e3).toISOString()

describe('haQuanto', () => {
  it('cobre nulo, agora, minutos, horas e dias', () => {
    expect(haQuanto(null, AGORA)).toBe('sem captura ainda')
    expect(haQuanto(iso(0.2), AGORA)).toBe('agora mesmo')
    expect(haQuanto(iso(7), AGORA)).toBe('há 7 min')
    expect(haQuanto(iso(125), AGORA)).toBe('há 2 h')
    expect(haQuanto(iso(60 * 50), AGORA)).toBe('há 2 d')
  })
})

describe('aoVivo', () => {
  it('é verdadeiro até 15 min', () => {
    expect(aoVivo(iso(14), AGORA)).toBe(true)
    expect(aoVivo(iso(16), AGORA)).toBe(false)
    expect(aoVivo(null, AGORA)).toBe(false)
  })
})

describe('resumoCamera', () => {
  const base = { id: 3, name: 'fixa-santos_gonzaga', descricao: 'Santos — Gonzaga', is_active: true }

  it('monta o card de uma câmera com captura', () => {
    const r = resumoCamera({ ...base, ultima_captura: { id: 9, captured_at: iso(3), weather_label: 'moderado', confidence: 0.812, modelo: 'fixa_f3' }, imagem_url: '/api/v1/captures/9/imagem' }, 'https://api', AGORA)
    expect(r.nome).toBe('Santos — Gonzaga')
    expect(r.categoria.label).toBe('Moderada')
    expect(r.confiancaPct).toBe(81)
    expect(r.quando).toBe('há 3 min')
    expect(r.aoVivo).toBe(true)
    expect(r.imagemSrc).toBe('https://api/api/v1/captures/9/imagem')
    expect(r.modelo).toBe('fixa_f3')
  })

  it('câmera sem captura não inventa nada', () => {
    const r = resumoCamera({ ...base, descricao: null, ultima_captura: null, imagem_url: null }, 'https://api', AGORA)
    expect(r.nome).toBe('santos_gonzaga')
    expect(r.categoria.label).toBe('Não medido')
    expect(r.confiancaPct).toBeNull()
    expect(r.quando).toBe('sem captura ainda')
    expect(r.imagemSrc).toBeNull()
  })

  it('rótulo nulo é "Não medido", nunca seco', () => {
    const r = resumoCamera({ ...base, ultima_captura: { id: 1, captured_at: iso(1), weather_label: null, confidence: null }, imagem_url: '/x' }, '', AGORA)
    expect(r.categoria.label).toBe('Não medido')
  })
})

describe('pontosSerie', () => {
  it('converte classes em níveis ordinais', () => {
    const p = pontosSerie([
      { captured_at: iso(3), weather_label: 'seco' },
      { captured_at: iso(2), weather_label: 'forte' },
      { captured_at: iso(1), weather_label: null },
    ])
    expect(p.map(x => x.nivel)).toEqual([0, 3, null])
    expect(p[2].rotulo).toBe('Não medido')
    expect(p[0].t).toBeLessThan(p[1].t)
  })
})
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd frontend && npm test`
Expected: FAIL (`Failed to resolve import "./cameras"`).

- [ ] **Step 4: Implementar** (`frontend/src/lib/cameras.js`)

```js
// Apresentação das câmeras fixas (GET /api/v1/cameras/). Funções puras: testadas com Vitest.
import { categoryFromLabel, UNMEASURED } from './categories'

export const MINUTOS_AO_VIVO = 15
const NIVEL = { dry: 0, drizzle: 1, moderate: 2, heavy: 3 }

export function haQuanto(iso, agora = new Date()) {
  if (!iso) return 'sem captura ainda'
  const min = (agora.getTime() - new Date(iso).getTime()) / 60e3
  if (min < 1) return 'agora mesmo'
  if (min < 60) return `há ${Math.floor(min)} min`
  if (min < 60 * 24) return `há ${Math.floor(min / 60)} h`
  return `há ${Math.floor(min / (60 * 24))} d`
}

export function aoVivo(iso, agora = new Date()) {
  if (!iso) return false
  return (agora.getTime() - new Date(iso).getTime()) / 60e3 <= MINUTOS_AO_VIVO
}

export function resumoCamera(cam, baseUrl, agora = new Date()) {
  const u = cam.ultima_captura
  return {
    id: cam.id,
    nome: cam.descricao || cam.name.replace(/^fixa-/, ''),
    descricao: cam.descricao,
    categoria: u ? categoryFromLabel(u.weather_label) : UNMEASURED,
    confiancaPct: u?.confidence != null ? Math.round(u.confidence * 100) : null,
    quando: haQuanto(u?.captured_at ?? null, agora),
    aoVivo: aoVivo(u?.captured_at ?? null, agora),
    imagemSrc: cam.imagem_url ? `${baseUrl}${cam.imagem_url}` : null,
    modelo: u?.modelo ?? null,
  }
}

export function pontosSerie(serie) {
  return serie.map(p => {
    const cat = categoryFromLabel(p.weather_label)
    return { t: new Date(p.captured_at).getTime(), nivel: NIVEL[cat.key] ?? null, cor: cat.color, rotulo: cat.label }
  })
}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd frontend && npm test && npm run lint`
Expected: testes passam; lint sem erro.

- [ ] **Step 6: CI** — no job `frontend` de `.github/workflows/ci.yml`, acrescentar `- run: npm test` depois do `npm run lint`.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/src/lib/cameras.js frontend/src/lib/cameras.test.js .github/workflows/ci.yml
git commit -m "feat(frontend): funções de apresentação das câmeras fixas com Vitest"
```

---

### Task 2: Página "Câmeras"

**Files:**
- Create: `frontend/src/hooks/useCameras.js`, `frontend/src/components/cameras/CameraCard.jsx`, `frontend/src/pages/Cameras.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/pages/Dashboard.jsx`

**Interfaces:**
- Consumes: `resumoCamera` (Task 1); `GET /api/v1/cameras/` (Plano A Task 6); `apiGet`, `BASE_URL` de `src/api/client.js`.
- Produces: `useCameras({ excluirDemo = false } = {}) -> { cameras: CameraResumo[], error, carregando, atualizadoEm, pollMs }` (poll `VITE_POLL_MS` ou 30 s); rota `/cameras`; link "Câmeras →" no cabeçalho do Dashboard (mesmo array dos links "Histórico →" e "Dispositivos →").

- [ ] **Step 1: Hook** (`frontend/src/hooks/useCameras.js`) — mesmo padrão de `useLiveCaptures.js`:

```js
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

const POLL_MS = Number(import.meta.env.VITE_POLL_MS) || 30_000

/** Câmeras fixas com a última captura classificada (GET /api/v1/cameras/). */
export function useCameras({ excluirDemo = false } = {}) {
  const [cameras, setCameras] = useState([])
  const [atualizadoEm, setAtualizadoEm] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelado = false
    const buscar = () =>
      apiGet(`/api/v1/cameras/?excluir_demo=${excluirDemo}`)
        .then(d => { if (!cancelado) { setCameras(d); setAtualizadoEm(new Date()); setError(null) } })
        .catch(e => { if (!cancelado) setError(e) })
    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [excluirDemo])

  return { cameras, error, carregando: atualizadoEm === null && !error, atualizadoEm, pollMs: POLL_MS }
}
```

- [ ] **Step 2: Card** (`frontend/src/components/cameras/CameraCard.jsx`)

```jsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ImageOff } from 'lucide-react'

/** Card de uma câmera fixa: miniatura, classe do modelo, confiança e há quanto tempo. */
export default function CameraCard({ r }) {
  const [semImagem, setSemImagem] = useState(false)
  return (
    <Link to={`/cameras/${r.id}`} className="rounded-xl overflow-hidden flex flex-col"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)' }}>
      <div style={{ aspectRatio: '4 / 3', background: 'var(--bg-base)', position: 'relative' }}>
        {r.imagemSrc && !semImagem ? (
          <img src={r.imagemSrc} alt={`Último frame de ${r.nome}`} onError={() => setSemImagem(true)}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div className="flex flex-col items-center justify-center gap-1" style={{ height: '100%', color: 'var(--text-secondary)' }}>
            <ImageOff size={20} />
            <span className="font-mono text-xs">{r.imagemSrc ? 'imagem indisponível' : 'sem captura ainda'}</span>
          </div>
        )}
        <span className="font-mono text-xs px-2 py-1 rounded"
          style={{ position: 'absolute', top: 8, left: 8, background: r.categoria.color, color: '#0b1220' }}>
          {r.categoria.label}
        </span>
      </div>
      <div className="p-3 flex flex-col gap-1">
        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{r.nome}</span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          {r.quando}{r.confiancaPct != null && ` · confiança ${r.confiancaPct}%`}{r.aoVivo && ' · ao vivo'}
        </span>
      </div>
    </Link>
  )
}
```

- [ ] **Step 3: Página** (`frontend/src/pages/Cameras.jsx`)

```jsx
import { useMemo } from 'react'
import Topbar from '../components/layout/Topbar'
import CameraCard from '../components/cameras/CameraCard'
import { useCameras } from '../hooks/useCameras'
import { resumoCamera } from '../lib/cameras'
import { BASE_URL } from '../api/client'

/** Grade das câmeras fixas, classificadas pelo modelo fixo, atualizando sozinha. */
export default function Cameras() {
  const { cameras, error, carregando, pollMs } = useCameras()
  const resumos = useMemo(() => cameras.map(c => resumoCamera(c, BASE_URL)), [cameras])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb="Câmeras fixas" backTo="/dashboard" />
      <main className="p-6 flex flex-col gap-4">
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Transmissões públicas classificadas pelo modelo de câmera fixa · atualiza a cada {Math.round(pollMs / 1000)} s
        </p>
        {error && <p className="font-mono text-xs" style={{ color: 'var(--cat-heavy)' }}>Não consegui falar com a API ({error.message}). Tento de novo no próximo ciclo.</p>}
        {carregando && <p className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Carregando…</p>}
        {!carregando && !error && resumos.length === 0 && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Nenhuma câmera fixa cadastrada.</p>
        )}
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
          {resumos.map(r => <CameraCard key={r.id} r={r} />)}
        </div>
      </main>
    </div>
  )
}
```

Conferir as props reais do `Topbar` (`breadcrumb`, `backTo`) em `src/components/layout/Topbar.jsx` e ajustar se diferirem.

- [ ] **Step 4: Rota e link** — em `App.jsx`, `import Cameras from './pages/Cameras'` e `<Route path="/cameras" element={<Cameras />} />`. Em `Dashboard.jsx`, acrescentar `['/cameras', 'Câmeras →']` ao array de links do cabeçalho.

- [ ] **Step 5: Verificar**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: tudo sem erro. Depois, com o backend local do Plano A no ar e uma câmera cadastrada: `VITE_API_URL=http://localhost:8000 npm run dev` e abrir `/cameras` (o orquestrador confere com Playwright: card aparece, imagem carrega ou mostra "imagem indisponível").

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useCameras.js frontend/src/components/cameras/CameraCard.jsx frontend/src/pages/Cameras.jsx frontend/src/App.jsx frontend/src/pages/Dashboard.jsx
git commit -m "feat(frontend): página Câmeras com as câmeras fixas ao vivo"
```

---

### Task 3: Separar fixa de móvel no mapa e no histórico

**Files:**
- Modify: `frontend/src/hooks/useLiveCaptures.js`, `frontend/src/components/dashboard/MapaAoVivo.jsx`, `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/hooks/useHistorico.js`, `frontend/src/pages/Historico.jsx`

**Interfaces:**
- Consumes: `?tipo=movel|fixa` em `/captures` e `/stats/geo` (Plano A Task 5); `useCameras` (Task 2).
- Produces:
  - `useLiveCaptures` pede `tipo=movel` nas duas chamadas.
  - `MapaAoVivo({ capturas, ultimaConhecida, cameras = [] })`: camadas de câmeras fixas como **quadrado** (`L.divIcon`, 14×14 px, cor da categoria, borda escura) com `Tooltip` "nome · classe · há N min"; o carro continua com `CircleMarker` (círculo).
  - `useHistorico(periodo, resolucao, incluirDemo, tipo = null)`; na página Histórico, um seletor "Todas / Fixas / Móveis" ao lado dos filtros existentes, que passa `tipo` (`null`, `'fixa'`, `'movel'`).

- [ ] **Step 1:** em `useLiveCaptures.js`, trocar as duas URLs para incluir `&tipo=movel` (`/api/v1/captures/?limit=200&tipo=movel&from_date=...` e `/api/v1/captures/?limit=1&tipo=movel`). Comentário: "câmeras fixas têm página própria; aqui é só o trajeto do carro".
- [ ] **Step 2:** em `MapaAoVivo.jsx`, importar `Marker` de `react-leaflet`, `L` de `leaflet` e `resumoCamera` de `../../lib/cameras`. Acrescentar a prop `cameras` e, dentro do `MapContainer`, depois do trajeto:

```jsx
{cameras.filter(c => c.latitude != null).map(c => {
  const r = resumoCamera(c, '')
  const icone = L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;background:${r.categoria.color};border:2px solid #0b1220;border-radius:2px"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
  return (
    <Marker key={`cam-${c.id}`} position={[c.latitude, c.longitude]} icon={icone}>
      <Tooltip>{r.nome} · {r.categoria.label} · {r.quando}</Tooltip>
    </Marker>
  )
})}
```

Em `Dashboard.jsx`: `const { cameras } = useCameras()` e `<MapaAoVivo capturas={recentes} ultimaConhecida={ultima} cameras={cameras} />`. O `Seguir` continua enquadrando só o carro.
- [ ] **Step 3:** em `useHistorico.js`, acrescentar o parâmetro `tipo = null`, incluí-lo na `chave` e passá-lo no `query(...)` das duas chamadas (`tipo` some do query quando é `null`, pelo filtro de `null` que já existe em `query`). Em `Historico.jsx`, estado `const [tipo, setTipo] = useState(null)` e três botões no mesmo estilo dos botões de período: `Todas` (`null`), `Fixas` (`'fixa'`), `Móveis` (`'movel'`).
- [ ] **Step 4: Verificar** — `npm test && npm run lint && npm run build` sem erro. Com o backend local e uma câmera fixa enviando: o trajeto do Dashboard não conecta pontos da câmera; o quadrado aparece no lugar da câmera; o Histórico muda ao trocar o filtro.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks frontend/src/components/dashboard/MapaAoVivo.jsx frontend/src/pages/Dashboard.jsx frontend/src/pages/Historico.jsx
git commit -m "feat(frontend): câmeras fixas no mapa (quadrado) e filtro fixa/móvel no histórico"
```

---

### Task 4: Detalhe da câmera com série das últimas horas

**Files:**
- Create: `frontend/src/hooks/useSerieCamera.js`, `frontend/src/pages/CameraDetalhe.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `GET /api/v1/cameras/{id}/serie?horas=N` (Plano A Task 6); `pontosSerie`, `resumoCamera` (Task 1); `useCameras` (Task 2) para o cabeçalho.
- Produces: `useSerieCamera(id, horas) -> { serie, error, carregando }` (poll igual ao `useCameras`); rota `/cameras/:id` (lazy, como o Histórico, por causa do recharts).

- [ ] **Step 1:** hook no padrão do `useCameras`, com URL `/api/v1/cameras/${id}/serie?horas=${horas}` e dependências `[id, horas]`.
- [ ] **Step 2:** página:
  - Cabeçalho: nome, descrição, link "abrir transmissão" para `stream_url` (`target="_blank" rel="noopener"`), a miniatura grande da última captura (com o mesmo fallback do card) e a classe atual.
  - Seletor de janela `3 h / 6 h / 24 h`.
  - Gráfico recharts `ScatterChart` (ou `LineChart` com `type="stepAfter"`) com eixo x em tempo (`t`, formatado `HH:mm`) e eixo y em categorias fixas (`ticks [0,1,2,3]`, rótulos Seco/Garoa/Moderada/Forte), cada ponto pintado com `cor`; pontos `nivel == null` ficam numa faixa "Não medido" abaixo do 0 ou são omitidos com uma legenda "N capturas sem medida". Um eixo y só.
  - Texto curto abaixo: "Previsão do modelo fixo (`<modelo>`). A leitura do pluviômetro aparece aqui quando a integração das estações estiver ativa." (se o Plano A Task 8 for feito, trocar por um segundo gráfico **empilhado** com o mm/h da estação).
- [ ] **Step 3:** em `App.jsx`, `const CameraDetalhe = lazy(() => import('./pages/CameraDetalhe'))` e `<Route path="/cameras/:id" element={<CameraDetalhe />} />`; no card (Task 2) o `Link` já aponta para essa rota.
- [ ] **Step 4: Verificar** — `npm test && npm run lint && npm run build`; abrir `/cameras/<id>` com dados locais e conferir o gráfico com o orquestrador (Playwright, screenshot).
- [ ] **Step 5: Commit** `feat(frontend): detalhe da câmera fixa com a série das últimas horas`.

---

### Task 5: Replay de chuva real pelas câmeras (demo)

**Files:**
- Create: `ml/scripts/coleta_fixa/replay_evento.py`
- Test: `ml/tests/test_replay_evento.py`

**Interfaces:**
- Consumes: `metadados_ingest`, `enviar_frame`, `token_da_fonte`, `nome_device` de `coletor.py` (Plano B Task 1).
- Produces:
  - `com_marca_de_replay(jpeg: bytes, marca: str) -> bytes` — insere um segmento COM (`0xFFFE`) logo depois do SOI com `cityrain-replay:<marca>`; os pixels não mudam, o sha256 muda.
  - `selecionar_frames(manifest: Path, camera: str, de: datetime | None, ate: datetime | None, raiz_frames: Path) -> list[Path]` — `.jpg` da câmera no intervalo, em ordem de tempo, só os que existem em disco.
  - `preparar_frame_replay(jpg: Path, destino: Path, agora: datetime, marca: str) -> Path` — copia o par para uma pasta temporária com `capturado_em_utc = agora` e JPEG marcado; devolve o novo `.jpg`.
  - CLI: `replay_evento.py --camera bc_atlantica [--de ISO --ate ISO] [--intervalo 2] [--api URL] [--tokens PATH] [--manifest ml/data/manifests/manifest_coleta_fixa.csv]`. Envia cada frame com `demo={"origem": "replay_evento", "camera": <id>, "capturado_originalmente": <ISO>}`. Token pela câmera (`token_da_fonte`).

- [ ] **Step 1: Testes que falham** (`ml/tests/test_replay_evento.py`)

```python
"""Replay de um evento real pelas câmeras fixas, para a demonstração."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

_DIR = Path(__file__).resolve().parents[1] / "scripts" / "coleta_fixa"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("replay_evento", _DIR / "replay_evento.py")
rp = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rp
_spec.loader.exec_module(rp)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.fromarray((np.random.default_rng(0).random((24, 32, 3)) * 255).astype(np.uint8)).save(buf, "JPEG")
    return buf.getvalue()


def test_marca_muda_o_hash_e_preserva_os_pixels():
    original = _jpeg()
    marcado = rp.com_marca_de_replay(original, "2026-10-19T10:00:00Z")
    assert hashlib.sha256(marcado).hexdigest() != hashlib.sha256(original).hexdigest()
    assert marcado.startswith(b"\xff\xd8\xff\xfe")
    a = np.asarray(Image.open(io.BytesIO(original)))
    b = np.asarray(Image.open(io.BytesIO(marcado)))
    assert np.array_equal(a, b)
    assert rp.com_marca_de_replay(original, "x") != rp.com_marca_de_replay(original, "y")


def _par(pasta: Path, nome: str, ts: str):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.jpg").write_bytes(_jpeg())
    (pasta / f"{nome}.json").write_text(json.dumps({
        "schema": 2, "device_id": "cam1", "capturado_em_utc": ts, "arquivo": f"{nome}.jpg",
        "gps": {"latitude": -26.99, "longitude": -48.63, "ultimo_fix_em": ts, "fixo": True}}))


def test_seleciona_frames_da_camera_no_intervalo_em_ordem(tmp_path):
    raiz = tmp_path / "frames"
    _par(raiz / "cam1", "frame_b", "2026-10-01T10:05:00+00:00")
    _par(raiz / "cam1", "frame_a", "2026-10-01T10:00:00+00:00")
    _par(raiz / "cam1", "frame_c", "2026-10-01T12:00:00+00:00")
    man = tmp_path / "m.csv"
    with open(man, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["arquivo", "pasta", "ts_utc"])
        for nome, ts in [("frame_b.jpg", "2026-10-01T10:05:00Z"), ("frame_a.jpg", "2026-10-01T10:00:00Z"),
                         ("frame_c.jpg", "2026-10-01T12:00:00Z"), ("sumiu.jpg", "2026-10-01T10:01:00Z")]:
            wr.writerow([nome, "cam1", ts])
        wr.writerow(["frame_x.jpg", "outra", "2026-10-01T10:02:00Z"])
    de = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    ate = datetime(2026, 10, 1, 11, tzinfo=timezone.utc)
    sel = rp.selecionar_frames(man, "cam1", de, ate, raiz)
    assert [p.name for p in sel] == ["frame_a.jpg", "frame_b.jpg"]


def test_prepara_frame_com_horario_atual_e_jpeg_marcado(tmp_path):
    _par(tmp_path / "orig", "frame_a", "2026-10-01T10:00:00+00:00")
    agora = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)
    novo = rp.preparar_frame_replay(tmp_path / "orig/frame_a.jpg", tmp_path / "tmp", agora, "m1")
    meta = json.loads(novo.with_suffix(".json").read_text())
    assert meta["capturado_em_utc"] == agora.isoformat()
    assert meta["capturado_originalmente"] == "2026-10-01T10:00:00+00:00"
    assert novo.read_bytes() != (tmp_path / "orig/frame_a.jpg").read_bytes()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_replay_evento.py`
Expected: FAIL (script não existe).

- [ ] **Step 3: Implementar** (`ml/scripts/coleta_fixa/replay_evento.py`)

```python
#!/usr/bin/env python3
"""Replay de uma chuva real gravada por uma câmera fixa, pelo pipeline de produção (spec CF8).

Cada frame do evento é reenviado ao POST /api/v1/ingest como se fosse agora, com
`metadata.demo` (o histórico exclui demo). O backend deduplica por sha256 da imagem,
então cada envio ganha um comentário JPEG com a hora do replay: os pixels são os
mesmos, o hash não, e o replay pode ser ensaiado quantas vezes for preciso.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/replay_evento.py --camera bc_atlantica \
        --de 2026-10-01T18:00:00-03:00 --ate 2026-10-01T19:00:00-03:00 --intervalo 2
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from coletor import enviar_frame, token_da_fonte  # noqa: E402


def com_marca_de_replay(jpeg: bytes, marca: str) -> bytes:
    """Insere um segmento COM logo após o SOI; não toca nos dados da imagem."""
    if not jpeg.startswith(b"\xff\xd8"):
        raise ValueError("não é JPEG")
    texto = f"cityrain-replay:{marca}".encode()
    seg = b"\xff\xfe" + (len(texto) + 2).to_bytes(2, "big") + texto
    return jpeg[:2] + seg + jpeg[2:]


def _quando(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def selecionar_frames(manifest: Path, camera: str, de: datetime | None, ate: datetime | None, raiz_frames: Path) -> list[Path]:
    with open(manifest, newline="") as f:
        linhas = [r for r in csv.DictReader(f) if r["pasta"] == camera]
    escolhidos = []
    for r in sorted(linhas, key=lambda r: r["ts_utc"]):
        t = _quando(r["ts_utc"])
        if (de and t < de) or (ate and t > ate):
            continue
        p = raiz_frames / camera / r["arquivo"]
        if p.is_file() and p.with_suffix(".json").is_file():
            escolhidos.append(p)
    return escolhidos


def preparar_frame_replay(jpg: Path, destino: Path, agora: datetime, marca: str) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    meta = json.loads(jpg.with_suffix(".json").read_text())
    meta["capturado_originalmente"] = meta["capturado_em_utc"]
    meta["capturado_em_utc"] = agora.isoformat()
    novo = destino / jpg.name
    novo.write_bytes(com_marca_de_replay(jpg.read_bytes(), marca))
    novo.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False))
    return novo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--de")
    ap.add_argument("--ate")
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--manifest", type=Path, default=RAIZ / "ml/data/manifests/manifest_coleta_fixa.csv")
    ap.add_argument("--raiz-frames", type=Path, default=RAIZ / "ml/data/raw/coleta_fixa")
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/coleta_fixa.yaml")
    ap.add_argument("--tokens", type=Path, default=RAIZ / "ml/configs/coleta_fixa_tokens.json")
    ap.add_argument("--api", help="URL do /ingest (default: backend_url do YAML)")
    args = ap.parse_args()

    url = args.api or yaml.safe_load(args.config.read_text())["backend_url"]
    token = token_da_fonte(args.camera, args.tokens)
    if not token:
        sys.exit(f"sem token para {args.camera}: defina CITYRAIN_TOKEN_{args.camera.upper()} ou {args.tokens}")
    frames = selecionar_frames(args.manifest, args.camera, _quando(args.de) if args.de else None,
                               _quando(args.ate) if args.ate else None, args.raiz_frames)
    print(f"[replay] {len(frames)} frames de {args.camera} -> {url}", flush=True)
    tmp = Path(tempfile.mkdtemp(prefix="replay_"))
    try:
        for jpg in frames:
            agora = datetime.now(timezone.utc)
            novo = preparar_frame_replay(jpg, tmp, agora, agora.isoformat())
            original = json.loads(novo.with_suffix(".json").read_text())["capturado_originalmente"]
            demo = {"origem": "replay_evento", "camera": args.camera, "capturado_originalmente": original}
            status = enviar_frame(novo, url, token, demo=demo)
            print(f"  {jpg.name} (gravado {original}) -> {status or 'sem rede'}", flush=True)
            time.sleep(args.intervalo)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_replay_evento.py ml/tests/test_coleta_fixa.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/coleta_fixa/replay_evento.py ml/tests/test_replay_evento.py
git commit -m "feat(demo): replay de chuva real pelas câmeras fixas no pipeline de produção"
```

---

### Task 6: Roteiro da demo da câmera fixa

**Files:**
- Modify: `docs/roteiro-demo-defesa.md`

- [ ] **Step 1:** acrescentar a seção "Câmera fixa (~3 min)" com:
  1. **Antes (no dia):** `coletor.py ml/configs/coleta_fixa.yaml --enviar --intervalo-s 60` rodando no Mac com `caffeinate -i`; abrir `/cameras` com `VITE_POLL_MS=5000`.
  2. **Ao vivo:** mostrar a grade; abrir uma câmera e a transmissão original lado a lado; se não estiver chovendo, mostrar o `seco` correto.
  3. **Replay:** escolher **antes** um evento com moderada/forte (o resumo do `montar_splits_fixa.py` lista as câmeras com essas classes), rodar `replay_evento.py --camera <id> --de ... --ate ... --intervalo 2` e mostrar a classe subindo no detalhe da câmera.
  4. **Frase para a banca:** "cada frame atravessou a API pública e foi classificado pelo modelo de câmera fixa, treinado só com chuva real medida por pluviômetro. O teste foi por evento e numa câmera que o modelo nunca viu."
  5. **Plano B se a rede cair:** backend local (`docs/COMO-CONTINUAR.md`) com o mesmo replay.
- [ ] **Step 2:** ensaiar no dia 19/10 (orquestrador + Rodrigo) e anotar o tempo real.
- [ ] **Step 3: Commit** `docs: roteiro da demonstração da câmera fixa`.
