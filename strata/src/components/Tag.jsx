export default function Tag({ children, color = 'text-text-secondary border-border' }) {
  return (
    <span className={`text-xs font-mono border rounded px-1.5 py-0.5 whitespace-nowrap ${color}`}>
      {children}
    </span>
  )
}
