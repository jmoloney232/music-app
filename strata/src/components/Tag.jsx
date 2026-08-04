import { keyColor } from '../utils/camelot'

// Two forms rather than two colours: mono + hairline reads as measured data,
// filled reads as a category the catalogue assigned.
export default function Tag({ children, variant = 'data', camelot = null, compatible = false }) {
  const base = 'inline-flex items-center gap-1.5 rounded-chip px-1.5 py-0.5 text-xs whitespace-nowrap'

  if (variant === 'label') {
    return <span className={`${base} bg-sunken text-ink-quiet`}>{children}</span>
  }

  // A compatible key is the one thing on this row a DJ is actually deciding on,
  // so it gets weight, a border step and a glyph — never colour on its own.
  const emphasis = compatible
    ? 'border-line-control font-medium text-ink'
    : 'border-hairline text-ink-quiet'

  return (
    <span className={`${base} border font-mono tabular-nums ${emphasis}`}>
      {camelot && (
        <span
          aria-hidden="true"
          className="h-2.5 w-2.5 flex-shrink-0 rounded-[1px]"
          style={{ backgroundColor: keyColor(camelot) }}
        />
      )}
      {children}
      {compatible && (
        <>
          <span aria-hidden="true" className="text-accent">↔</span>
          <span className="sr-only">— mixes with the query key</span>
        </>
      )}
    </span>
  )
}
