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

function clamp01(x) {
  return x < 0 ? 0 : x > 1 ? 1 : x
}

function oklchToHex(L, C, hueDeg) {
  const h = (hueDeg * Math.PI) / 180
  const a = C * Math.cos(h)
  const b = C * Math.sin(h)

  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3

  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]

  return (
    '#' +
    lin
      .map(c => {
        const v = clamp01(c)
        const srgb = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055
        return Math.round(clamp01(srgb) * 255)
          .toString(16)
          .padStart(2, '0')
      })
      .join('')
      .toUpperCase()
  )
}

// Holding lightness constant across all 12 hues is what keeps contrast even.
// An HSL ramp at fixed L measures anywhere from 1.4:1 to 3.8:1 against the page
// depending on hue, so a single label colour can't be legible on all of them.
const KEY_TONES = {
  major:    { L: 0.8,  C: 0.075 },
  minor:    { L: 0.68, C: 0.085 },
  // 0.52 rather than 0.55 so white labels clear 4.5:1 on all twelve hues,
  // not just the darker half of the ring.
  selected: { L: 0.52, C: 0.13 },
}

// Position on the wheel (1-12) sets the hue; A/B sets the tone.
export function keyColor(camelot, tone) {
  if (!camelot) return null
  const m = camelot.match(/^(\d+)([AB])$/)
  if (!m) return null
  const pos = parseInt(m[1])
  if (pos < 1 || pos > 12) return null

  const ramp = KEY_TONES[tone] ?? (m[2] === 'A' ? KEY_TONES.minor : KEY_TONES.major)
  return oklchToHex(ramp.L, ramp.C, ((pos - 1) * 30 + 20) % 360)
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
