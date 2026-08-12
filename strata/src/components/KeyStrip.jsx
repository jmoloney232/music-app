import { keyColor } from '../utils/camelot'

/**
 * A playlist's harmonic fingerprint, drawn from the keys of the tracks actually
 * in it. This is the collection artwork — derived from catalogue data rather
 * than invented, so an empty playlist correctly shows nothing.
 */
export default function KeyStrip({ camelots = [], limit = 16 }) {
  const keys = camelots.filter(Boolean).slice(0, limit)
  if (keys.length === 0) return null

  return (
    <div
      className="flex h-2 gap-px overflow-hidden rounded-chip"
      role="img"
      aria-label={`Keys in this collection: ${keys.join(', ')}`}
    >
      {keys.map((c, i) => (
        <span
          key={`${c}-${i}`}
          className="h-full flex-1"
          style={{ backgroundColor: keyColor(c) }}
        />
      ))}
    </div>
  )
}
