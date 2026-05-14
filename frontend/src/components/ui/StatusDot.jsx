export default function StatusDot({ status, label }) {
  const color = status === 'online' ? 'var(--cat-dry)' : 'var(--cat-heavy)'
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      <span
        className="inline-block w-2 h-2 rounded-full"
        style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}` }}
      />
      <span style={{ color }}>{label ?? (status === 'online' ? 'Online' : 'Offline')}</span>
    </span>
  )
}
