// Placeholders de carregamento (ver .skeleton em index.css, que respeita prefers-reduced-motion).
export function Skeleton({ className = '', style }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />
}

/** Placeholder com a mesma silhueta do CameraCard. */
export function CameraCardSkeleton() {
  return (
    <div className="rounded-xl overflow-hidden flex flex-col" aria-hidden="true"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)' }}>
      <Skeleton style={{ aspectRatio: '4 / 3', borderRadius: 0 }} />
      <div className="p-3 flex flex-col gap-2">
        <Skeleton style={{ height: 14, width: '70%' }} />
        <Skeleton style={{ height: 12, width: '45%' }} />
      </div>
    </div>
  )
}
