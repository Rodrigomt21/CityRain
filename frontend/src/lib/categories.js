// Definição das categorias de intensidade de chuva.
// Limiares = os do dataset e do modelo (ml/configs/rotulagem_imt.yaml):
//   seco = 0 | garoa: 0 < i <= 2,5 | moderada: 2,5 < i <= 10 | forte: > 10 mm/h
// Mudar aqui sem mudar lá faz o mapa contradizer o modelo.
export const CATEGORIES = {
  dry:      { key: 'dry',      label: 'Seco',     min: 0,    max: 0,        color: '#22c55e', cssVar: '--cat-dry'      },
  drizzle:  { key: 'drizzle',  label: 'Garoa',    min: 0,    max: 2.5,      color: '#67e8f9', cssVar: '--cat-drizzle'  },
  moderate: { key: 'moderate', label: 'Moderada', min: 2.5,  max: 10,       color: '#fb923c', cssVar: '--cat-moderate' },
  heavy:    { key: 'heavy',    label: 'Forte',    min: 10,   max: Infinity, color: '#ef4444', cssVar: '--cat-heavy'    },
}

// Captura recebida sem intensidade (weather_label nulo): o backend ainda não
// classificou. Nunca exibir como "Seco" — seco é afirmação, isto é ausência de medida.
export const UNMEASURED = { key: 'unmeasured', label: 'Não medido', color: '#64748b', cssVar: '--cat-unmeasured' }

// Intervalos (min, max]: 0 é seco; qualquer chuva medida é no mínimo garoa.
export function getCategory(mmh) {
  if (!(mmh > 0)) return CATEGORIES.dry
  if (mmh <= CATEGORIES.drizzle.max) return CATEGORIES.drizzle
  if (mmh <= CATEGORIES.moderate.max) return CATEGORIES.moderate
  return CATEGORIES.heavy
}

// weather_label do backend -> categoria. O backend grava "moderado"; o ML usa "moderada".
const LABEL_TO_KEY = {
  seco: 'dry',
  garoa: 'drizzle',
  moderado: 'moderate',
  moderada: 'moderate',
  forte: 'heavy',
}

export function categoryFromLabel(label) {
  const key = LABEL_TO_KEY[(label ?? '').toLowerCase()]
  return key ? CATEGORIES[key] : UNMEASURED
}

// Ordem de severidade decrescente — útil para ordenar alertas e status global.
// 'unmeasured' fica fora de propósito: não é mais nem menos grave que uma classe
// real, é ausência de medida.
export const SEVERITY_ORDER = ['heavy', 'moderate', 'drizzle', 'dry']

export function getMostSevereCategory(categories) {
  for (const key of SEVERITY_ORDER) {
    if (categories.includes(key)) return CATEGORIES[key]
  }
  // Nenhuma classe real presente: lista vazia (nada online) ou só 'unmeasured'.
  // Mesmo princípio do UNMEASURED acima — sem medida que sustente, não afirmar "Seco".
  return UNMEASURED
}
