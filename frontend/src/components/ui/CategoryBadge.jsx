export default function CategoryBadge({ category, size = 'sm' }) {
  if (!category) return null

  const pad = size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-xs'

  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-mono font-semibold uppercase tracking-wider ${pad}`}
      style={{
        color: category.color,
        backgroundColor: `${category.color}1a`,
        border: `1px solid ${category.color}4d`,
        boxShadow: `0 0 8px ${category.color}33`,
      }}
    >
      {category.label}
    </span>
  )
}
