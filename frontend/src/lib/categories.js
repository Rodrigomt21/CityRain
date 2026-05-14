// Definição das categorias de intensidade de chuva — não alterar os limiares
export const CATEGORIES = {
  dry:      { key: 'dry',      label: 'Seco',     min: 0,    max: 0.1,      color: '#22c55e', cssVar: '--cat-dry'      },
  drizzle:  { key: 'drizzle',  label: 'Garoa',    min: 0.1,  max: 5,        color: '#67e8f9', cssVar: '--cat-drizzle'  },
  moderate: { key: 'moderate', label: 'Moderada', min: 5,    max: 25,       color: '#fb923c', cssVar: '--cat-moderate' },
  heavy:    { key: 'heavy',    label: 'Forte',    min: 25,   max: Infinity, color: '#ef4444', cssVar: '--cat-heavy'    },
}

export function getCategory(mmh) {
  return Object.values(CATEGORIES).find(c => mmh >= c.min && mmh < c.max) ?? CATEGORIES.dry
}

// Ordem de severidade decrescente — útil para ordenar alertas e status global
export const SEVERITY_ORDER = ['heavy', 'moderate', 'drizzle', 'dry']

export function getMostSevereCategory(categories) {
  for (const key of SEVERITY_ORDER) {
    if (categories.includes(key)) return CATEGORIES[key]
  }
  return CATEGORIES.dry
}
