import { keyColor } from '../utils/camelot'

/**
 * A collection's harmonic fingerprint: twelve fixed ticks, one per wheel
 * position, lit for positions present in the collection. Fixed positions
 * rather than one bar per track, so a collection's harmonic spread reads at a
 * glance — and an empty collection shows twelve unlit ticks instead of nothing.
 */
export default function KeyStrip({ camelots = [] }) {
  const present = new Set(
    camelots
      .filter(Boolean)
      .map(c => parseInt(c))
      .filter(n => n >= 1 && n <= 12),
  )

  return (
    <div
      className="flex gap-1"
      role="img"
      aria-label={
        present.size === 0
          ? 'No keys in this collection yet'
          : `Wheel positions in this collection: ${[...present].sort((a, b) => a - b).join(', ')}`
      }
    >
      {Array.from({ length: 12 }, (_, i) => {
        const pos = i + 1
        const lit = present.has(pos)
        return (
          <span
            key={pos}
            className="h-[18px] w-[2px]"
            style={{ backgroundColor: lit ? keyColor(`${pos}A`, 'selected') : '#2D2B2B' }}
          />
        )
      })}
    </div>
  )
}
