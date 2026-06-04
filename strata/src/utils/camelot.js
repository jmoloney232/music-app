export const CAMELOT_TO_KEY = {
  '1A': 'Ab minor',  '1B': 'B major',
  '2A': 'Eb minor',  '2B': 'Gb major',
  '3A': 'Bb minor',  '3B': 'Db major',
  '4A': 'F minor',   '4B': 'Ab major',
  '5A': 'C minor',   '5B': 'Eb major',
  '6A': 'G minor',   '6B': 'Bb major',
  '7A': 'D minor',   '7B': 'F major',
  '8A': 'A minor',   '8B': 'C major',
  '9A': 'E minor',   '9B': 'G major',
  '10A': 'B minor',  '10B': 'D major',
  '11A': 'F# minor', '11B': 'A major',
  '12A': 'C# minor', '12B': 'E major',
}

export function formatKey(camelot) {
  if (!camelot) return null
  const standard = CAMELOT_TO_KEY[camelot]
  return standard ? `${camelot} / ${standard}` : camelot
}

// Returns [same, parallel, -1 step, +1 step] — standard harmonic mixing compatibility
export function compatibleKeys(camelot) {
  if (!camelot) return []
  const m = camelot.match(/^(\d+)([AB])$/)
  if (!m) return [camelot]
  const n = parseInt(m[1])
  const ring = m[2]
  const alt = ring === 'A' ? 'B' : 'A'
  const prev = ((n - 2 + 12) % 12) + 1
  const next = (n % 12) + 1
  return [camelot, `${n}${alt}`, `${prev}${ring}`, `${next}${ring}`]
}
