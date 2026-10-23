import { Link } from 'react-router-dom'
import { CATEGORIES } from '../lib/categories'

// Página de entrada para o público (EUREKA). Tudo aqui é material do projeto: fotos tiradas pela câmera do
// carro (placas borradas, faixa do painel cortada), leituras das estações e datas do histórico do TCC.
// Números das estações: README ("O problema e a proposta"); fotos em public/diario/.

const FOTOS = [
  {
    src: '/diario/seco-0408.jpg', classe: CATEGORIES.dry,
    quando: '04/08/2026 · 08:25', onde: 'Mooca',
    leitura: 'estações da região: 0 mm/h',
  },
  {
    src: '/diario/garoa-1309.jpg', classe: CATEGORIES.drizzle,
    quando: '13/09/2026 · 16:51', onde: 'Parque da Mooca',
    leitura: 'estações da região: 1,2 mm/h',
  },
  {
    src: '/diario/chuva-2309.jpg', classe: CATEGORIES.moderate, rotulo: 'Moderada a forte',
    quando: '23/09/2026 · 09:50', onde: 'Mooca',
    leitura: 'estações perto do trajeto: 6 a 19 mm/h',
  },
]

// Datas e fatos do histórico do projeto (sessões de coleta, decisões do orientador, resultados).
const DIARIO = [
  ['04/08', 'Primeira volta com a câmera no para-brisa. Dia seco, 1.017 fotos e nenhuma gota.'],
  ['01/09', 'Primeiro dia com GPS funcionando: 4.643 fotos, cada uma com lugar e hora. Sem posição, não dá para saber qual estação comparar.'],
  ['13/09', 'Primeira garoa de verdade. As estações marcaram 1,2 mm/h; quase não se vê no vidro.'],
  ['23/09', 'A chuva mais forte que pegamos com o carro: de 6 a 19 mm/h nas estações perto do trajeto. A Jetson desligava sozinha; a culpa era o start-stop do carro e a tomada do acendedor.'],
  ['08/10', 'O orientador apontou que misturar câmera de carro com câmera de rua num modelo só não se sustentava. Viraram dois modelos.'],
  ['14/10', 'Chuva gerada por computador ficou de fora: só foto real, com rótulo de pluviômetro ou de radar meteorológico.'],
  ['16/10', 'Achamos vídeos de câmera veicular no YouTube com data e hora gravadas na imagem. Cruzando com o radar, ganhamos temporais de verdade para treinar.'],
  ['17/10', 'A conclusão mais honesta até agora: o modelo do carro ainda erra a intensidade em dias que nunca viu. O que falta são mais dias de chuva, não mais fotos.'],
]

const NUMEROS = [
  ['110', 'estações públicas de chuva na capital (CEMADEN, CGE e INMET)'],
  ['14 km²', 'para cada estação, em média'],
  ['45%', 'da cidade fica a mais de 2 km da estação mais próxima'],
  ['4', 'níveis que o modelo reconhece: seco, garoa, moderada e forte'],
]

const EQUIPE = 'Gabriel Moreno, Guilherme Mattioli, Paulo Vespero e Rodrigo Teixeira'

const T = {
  fundo: '#101214', superficie: '#16191c', linha: '#2a2e33',
  texto: '#ecebe6', suave: '#a3a29b', serif: "'Newsreader', Georgia, serif", mono: "'JetBrains Mono', monospace",
}

function Escala({ altura = 4 }) {
  // a marca do projeto: as quatro classes, da seca à forte
  return (
    <div aria-hidden style={{ display: 'flex', height: altura, width: 72 }}>
      {['dry', 'drizzle', 'moderate', 'heavy'].map(k => <span key={k} style={{ flex: 1, background: CATEGORIES[k].color }} />)}
    </div>
  )
}

function Botoes() {
  return (
    <div className="flex flex-col sm:flex-row gap-3">
      <Link to="/apresentacao" className="no-underline text-center"
        style={{ background: T.texto, color: T.fundo, padding: '13px 22px', borderRadius: 6, fontFamily: T.mono, fontSize: 14, fontWeight: 600 }}>
        Ver a chuva agora →
      </Link>
      <Link to="/simulacao" className="no-underline text-center"
        style={{ color: T.texto, padding: '12px 22px', borderRadius: 6, border: `1px solid ${T.linha}`, fontFamily: T.mono, fontSize: 14 }}>
        Simular a cidade conectada
      </Link>
    </div>
  )
}

function Foto({ src, alt, legenda, prioridade }) {
  return (
    <figure style={{ margin: 0 }}>
      <img src={src} alt={alt} loading={prioridade ? 'eager' : 'lazy'} width={640} height={440}
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 4 }} />
      <figcaption style={{ fontFamily: T.mono, fontSize: 12, color: T.suave, marginTop: 8, lineHeight: 1.5 }}>{legenda}</figcaption>
    </figure>
  )
}

function Secao({ titulo, children, id }) {
  return (
    <section id={id} className="px-4 sm:px-8 py-14 sm:py-20" style={{ borderTop: `1px solid ${T.linha}` }}>
      <div className="max-w-5xl mx-auto">
        <h2 style={{ fontFamily: T.serif, fontWeight: 500, fontSize: 'clamp(1.6rem, 4.5vw, 2.3rem)', color: T.texto, margin: '0 0 28px', lineHeight: 1.15 }}>
          {titulo}
        </h2>
        {children}
      </div>
    </section>
  )
}

export default function Landing() {
  return (
    <div style={{ background: T.fundo, color: T.texto, minHeight: '100vh' }}>
      <header className="px-4 sm:px-8 py-4 flex items-center justify-between gap-4" style={{ borderBottom: `1px solid ${T.linha}` }}>
        <div className="flex items-center gap-3">
          <Escala />
          <span style={{ fontFamily: T.mono, fontWeight: 700, fontSize: 15 }}>CityRain</span>
        </div>
        <span className="hidden sm:inline" style={{ fontFamily: T.mono, fontSize: 12, color: T.suave }}>
          TCC · Ciência da Computação · Instituto Mauá de Tecnologia · 2026
        </span>
        <Link to="/apresentacao" className="sm:hidden no-underline" style={{ fontFamily: T.mono, fontSize: 13, color: T.texto }}>Ao vivo →</Link>
      </header>

      <section className="px-4 sm:px-8 pt-10 pb-14 sm:pt-16 sm:pb-20">
        <div className="max-w-5xl mx-auto grid gap-10 md:grid-cols-[1.05fr_1fr] md:items-center">
          <div>
            <h1 style={{ fontFamily: T.serif, fontWeight: 500, fontSize: 'clamp(2.1rem, 7vw, 3.6rem)', lineHeight: 1.05, margin: 0, letterSpacing: '-0.01em' }}>
              São Paulo tem 1.522 km² e só 110 pluviômetros.
            </h1>
            <p style={{ fontSize: 18, lineHeight: 1.6, color: T.suave, margin: '22px 0 30px', maxWidth: 520 }}>
              Uma chuva forte cai num bairro e não aparece em estação nenhuma. A gente colocou uma câmera no
              para-brisa de um carro e saiu atrás de chuva: uma inteligência artificial olha cada foto e diz se está
              seco, garoando, chovendo moderado ou forte, e o mapa mostra onde.
            </p>
            <Botoes />
          </div>
          <Foto prioridade src="/diario/limpador-2309.jpg"
            alt="Foto tirada pela câmera do carro em dia de chuva, com o limpador passando no para-brisa"
            legenda="23/09/2026 · 10:02 · Av. Cassandoca, Mooca. Foto da nossa câmera no meio de uma passada do limpador." />
        </div>
      </section>

      <Secao titulo="O que a câmera vê">
        <div className="grid gap-8 sm:grid-cols-3">
          {FOTOS.map(f => (
            <div key={f.src}>
              <Foto src={f.src} alt={`Foto do para-brisa: ${f.rotulo ?? f.classe.label}`}
                legenda={`${f.quando} · ${f.onde} · ${f.leitura}`} />
              <span className="inline-flex items-center gap-2 mt-2" style={{ fontFamily: T.mono, fontSize: 13 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: f.classe.color }} />
                {f.rotulo ?? f.classe.label}
              </span>
            </div>
          ))}
        </div>
        <p style={{ color: T.suave, fontSize: 15, lineHeight: 1.6, margin: '28px 0 0', maxWidth: 640 }}>
          O rótulo de cada foto vem das estações públicas: a gente cruza o lugar e a hora da foto com o que o
          pluviômetro mediu ali perto. Na rua, o modelo vê só a imagem. As placas dos carros foram borradas.
        </p>
      </Secao>

      <Secao titulo="Diário de bordo">
        <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {DIARIO.map(([data, texto]) => (
            <li key={data} className="grid gap-1 sm:gap-8 sm:grid-cols-[88px_1fr] py-4" style={{ borderTop: `1px solid ${T.linha}` }}>
              <span style={{ fontFamily: T.mono, fontSize: 14, color: T.suave }}>{data}</span>
              <span style={{ fontSize: 17, lineHeight: 1.55 }}>{texto}</span>
            </li>
          ))}
        </ol>
      </Secao>

      <Secao titulo="Por que câmeras">
        <dl className="grid gap-x-10 gap-y-8 sm:grid-cols-2" style={{ margin: 0 }}>
          {NUMEROS.map(([n, txt]) => (
            <div key={n}>
              <dt style={{ fontFamily: T.serif, fontSize: 'clamp(2.4rem, 8vw, 3.4rem)', lineHeight: 1 }}>{n}</dt>
              <dd style={{ margin: '8px 0 0', color: T.suave, fontSize: 16, lineHeight: 1.5 }}>{txt}</dd>
            </div>
          ))}
        </dl>
        <p style={{ color: T.suave, fontSize: 15, lineHeight: 1.6, margin: '36px 0 0', maxWidth: 640 }}>
          Câmeras já estão em todo lugar: no carro, no poste, na janela. Cada foto classificada vira um ponto no mapa,
          com lugar e hora, agrupado em hexágonos de uns 460 m. A placa dentro do carro (uma Jetson Nano) descarta as
          fotos secas ali mesmo; as com chuva vão para o servidor, que estima a intensidade.
        </p>
      </Secao>

      <section className="px-4 sm:px-8 py-14 sm:py-20" style={{ borderTop: `1px solid ${T.linha}` }}>
        <div className="max-w-5xl mx-auto">
          <p style={{ fontFamily: T.serif, fontSize: 'clamp(1.5rem, 4.5vw, 2.1rem)', lineHeight: 1.25, margin: '0 0 26px', maxWidth: 640 }}>
            O mapa está ligado agora, com câmeras ao vivo e o nosso carro.
          </p>
          <Botoes />
        </div>
      </section>

      <footer className="px-4 sm:px-8 py-8" style={{ borderTop: `1px solid ${T.linha}`, background: T.superficie }}>
        <div className="max-w-5xl mx-auto flex flex-col gap-2" style={{ fontSize: 14, color: T.suave, lineHeight: 1.6 }}>
          <Escala altura={3} />
          <span style={{ color: T.texto }}>Feito por {EQUIPE}.</span>
          <span>Orientação: Prof. Gabriel de Souza Lima · TCC de Ciência da Computação, Instituto Mauá de Tecnologia, 2026.</span>
          <span>Dados de chuva: CEMADEN, CGE-SP e INMET.</span>
        </div>
      </footer>
    </div>
  )
}
