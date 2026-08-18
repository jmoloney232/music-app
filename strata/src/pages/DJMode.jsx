import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CAMELOT_TO_KEY, compatibleKeys } from '../utils/camelot'
import SpotifyButton from '../components/SpotifyButton'

const API = '/api'

// "D minor" -> "Dm", "F major" -> "F" — the compact form the wheel labels use.
function segName(camelot) {
  const full = CAMELOT_TO_KEY[camelot]
  if (!full) return ''
  const [note, type] = full.split(' ')
  return type === 'minor' ? `${note}m` : note
}

const VOCAL_LABEL = { instrumental: 'Instrumental', vocal: 'Vocal', ambiguous: 'Mixed' }

/**
 * The Camelot wheel as 24 circular buttons on two rings — outer major (B),
 * inner minor (A) — positioned by rotate/translate. Compatibility is answered
 * on the wheel itself: the selected key's partner and neighbours go gold, and
 * never by colour alone — each carries its state in the accessible name.
 */
function CamelotWheel({ selected, onSelect, trackCount, size }) {
  const s = size / 520
  const compat = selected ? new Set(compatibleKeys(selected)) : null

  const ring = (ringLetter, radius, diameter) =>
    Array.from({ length: 12 }, (_, i) => {
      const camelot = `${i + 1}${ringLetter}`
      const isSelected = camelot === selected
      const isCompat = !isSelected && compat?.has(camelot)
      const d = isSelected ? 70 * s : diameter * s
      const angle = i * 30

      return (
        <button
          key={camelot}
          aria-pressed={isSelected}
          aria-label={`${camelot}, ${CAMELOT_TO_KEY[camelot]}${
            isSelected ? ', selected' : isCompat ? `, mixes with ${selected}` : ''
          }`}
          onClick={() => onSelect(isSelected ? null : camelot)}
          className={`absolute left-1/2 top-1/2 flex flex-col items-center justify-center rounded-full
                      transition-colors ${
            isSelected
              ? 'border-2 border-accent bg-accent-fill text-accent-deep'
              : isCompat
                ? 'border border-accent text-accent hover:bg-accent-fill'
                : 'border border-[rgba(243,242,242,0.2)] text-ink-soft hover:border-accent hover:text-accent'
          }`}
          style={{
            width: d,
            height: d,
            margin: `${-d / 2}px 0 0 ${-d / 2}px`,
            transform: `rotate(${angle}deg) translateY(${-radius * s}px) rotate(${-angle}deg)`,
          }}
        >
          <span className={`leading-none tabular-nums ${isSelected ? 'text-[17px]' : 'text-[13px]'}`}
                style={{ fontSize: Math.max(10, (isSelected ? 17 : 13) * Math.max(s, 0.72)) }}>
            {camelot}
          </span>
          <span className="leading-tight text-current opacity-70"
                style={{ fontSize: Math.max(8, 9 * Math.max(s, 0.72)) }}>
            {segName(camelot)}
          </span>
        </button>
      )
    })

  return (
    <div
      role="group"
      aria-label="Camelot wheel"
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
    >
      <div
        aria-hidden="true"
        className="absolute left-1/2 top-1/2 rounded-full border border-divider"
        style={{ width: 504 * s, height: 504 * s, margin: `${-252 * s}px 0 0 ${-252 * s}px` }}
      />
      <div
        aria-hidden="true"
        className="absolute left-1/2 top-1/2 rounded-full border border-divider"
        style={{ width: 340 * s, height: 340 * s, margin: `${-170 * s}px 0 0 ${-170 * s}px` }}
      />

      {/* Centre disc: the current selection, or the prompt. */}
      <div
        className={`absolute left-1/2 top-1/2 flex flex-col items-center justify-center gap-[2px]
                    rounded-full border ${selected ? 'border-accent' : 'border-line-strong'}`}
        style={{ width: 176 * s, height: 176 * s, margin: `${-88 * s}px 0 0 ${-88 * s}px` }}
      >
        {selected ? (
          <>
            <span className="font-display font-light leading-none tabular-nums text-accent"
                  style={{ fontSize: 52 * Math.max(s, 0.72) }}>
              {selected}
            </span>
            <span className="text-sm text-ink-soft">{CAMELOT_TO_KEY[selected]}</span>
            {trackCount != null && (
              <span className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">
                {trackCount} track{trackCount === 1 ? '' : 's'}
              </span>
            )}
          </>
        ) : (
          <span className="text-sm text-ink-quiet">Pick a key</span>
        )}
      </div>

      {ring('B', 222, 56)}
      {ring('A', 142, 54)}
    </div>
  )
}

export default function DJMode() {
  const navigate = useNavigate()
  const [selectedKey, setSelectedKey] = useState(null)
  const [bpmMin, setBpmMin] = useState(80)
  const [bpmMax, setBpmMax] = useState(160)
  const [bpmEnabled, setBpmEnabled] = useState(false)
  const [tracks, setTracks] = useState([])
  const [loading, setLoading] = useState(false)
  const [slowLoad, setSlowLoad] = useState(false)
  const slowTimer = useRef(null)
  const latestRequest = useRef(0)

  // The wheel's geometry is in px, so its size steps down on narrow screens.
  const [wheelSize, setWheelSize] = useState(() =>
    typeof window !== 'undefined' && window.innerWidth < 640
      ? Math.min(340, window.innerWidth - 48)
      : 520,
  )
  useEffect(() => {
    const onResize = () =>
      setWheelSize(window.innerWidth < 640 ? Math.min(340, window.innerWidth - 48) : 520)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (loading) {
      slowTimer.current = setTimeout(() => setSlowLoad(true), 4000)
    } else {
      clearTimeout(slowTimer.current)
      setSlowLoad(false)
    }
    return () => clearTimeout(slowTimer.current)
  }, [loading])

  // Fetch the key unfiltered and narrow by tempo client-side: the centre disc
  // needs the key's full count and the list its filtered one, and one request
  // serves both.
  useEffect(() => {
    if (!selectedKey) { setTracks([]); return }
    // The timer is debounced but the responses are not ordered — without this
    // a slow early request can land after a newer one and show the wrong key.
    const requestId = ++latestRequest.current
    setLoading(true)
    fetch(`${API}/tracks/by-key?camelot=${selectedKey}`)
      .then(r => r.json())
      .then(d => { if (requestId === latestRequest.current) setTracks(d) })
      .catch(() => { if (requestId === latestRequest.current) setTracks([]) })
      .finally(() => { if (requestId === latestRequest.current) setLoading(false) })
  }, [selectedKey])

  const visibleTracks = bpmEnabled
    ? tracks.filter(t => t.bpm != null && t.bpm >= bpmMin && t.bpm <= bpmMax)
    : tracks

  return (
    <div className="mx-auto max-w-dense px-s4 pb-s6 pt-s5 sm:px-s6">
      <div className="grid grid-cols-1 gap-s5 lg:grid-cols-[1fr_480px] lg:gap-0">

        {/* Left: title + wheel */}
        <div className="flex flex-col items-center gap-[26px] lg:items-start lg:border-r lg:border-divider lg:pr-s6">
          <div className="flex w-full flex-col gap-[10px]">
            <h1 className="font-display text-[clamp(34px,5vw,52px)] font-light leading-none text-ink">
              {selectedKey ? (
                <>I'm in <span className="italic text-accent">{selectedKey}</span>{bpmEnabled ? <span className="tabular-nums"> at {bpmMin}–{bpmMax}</span> : null}.</>
              ) : (
                <>Pick a key.</>
              )}
            </h1>
            <p className="text-sm italic text-ink-quiet">
              Inner ring minor, outer ring major. Gold rings are what you can mix into.
            </p>
          </div>
          <CamelotWheel
            selected={selectedKey}
            onSelect={setSelectedKey}
            trackCount={selectedKey && !loading ? tracks.length : null}
            size={wheelSize}
          />
        </div>

        {/* Right: the key's tracks */}
        <div className="min-w-0 lg:pl-s6">
          <div className="mb-s3 flex flex-wrap items-baseline justify-between gap-s3 border-b border-line-strong pb-s3">
            <span className="font-display text-[30px] font-normal leading-none text-ink">
              {selectedKey
                ? loading ? `… in ${selectedKey}` : `${tracks.length} in ${selectedKey}`
                : 'No key selected'}
            </span>
            <label className="flex cursor-pointer select-none items-center gap-[9px] text-xs text-ink-soft">
              <input
                type="checkbox"
                checked={bpmEnabled}
                onChange={e => setBpmEnabled(e.target.checked)}
                className="h-3 w-3"
              />
              <span className="tabular-nums">{bpmMin}–{bpmMax} only</span>
            </label>
          </div>

          <div
            className={`mb-s4 flex items-center gap-s3 transition-opacity ${
              bpmEnabled ? 'opacity-100' : 'pointer-events-none opacity-40'
            }`}
          >
            <span className="w-8 text-right text-sm tabular-nums text-ink">{bpmMin}</span>
            <input
              type="range" min={60} max={215} value={bpmMin}
              aria-label="Minimum BPM"
              onChange={e => setBpmMin(Math.min(+e.target.value, bpmMax - 5))}
              className="flex-1"
            />
            <span className="text-xs text-ink-quiet">–</span>
            <input
              type="range" min={65} max={220} value={bpmMax}
              aria-label="Maximum BPM"
              onChange={e => setBpmMax(Math.max(+e.target.value, bpmMin + 5))}
              className="flex-1"
            />
            <span className="w-8 text-sm tabular-nums text-ink">{bpmMax}</span>
          </div>

          {!selectedKey ? (
            <div className="rounded border border-dashed border-line-strong px-s4 py-s6 text-center">
              <p className="text-sm font-medium text-ink">Nothing to list yet</p>
              <p className="mx-auto mt-1 max-w-[260px] text-xs leading-relaxed text-ink-quiet">
                Click any ring on the wheel to see every track in that key, sorted by tempo.
              </p>
            </div>
          ) : loading ? (
            <div className="flex flex-col items-center gap-s3 py-s6">
              <div
                role="status"
                className="h-6 w-6 animate-spin rounded-full border-2 border-line-strong border-t-accent"
              />
              {slowLoad && (
                <p className="text-sm italic text-ink-quiet">
                  Waking up the server — first load can take up to 30s…
                </p>
              )}
            </div>
          ) : visibleTracks.length === 0 ? (
            <div className="py-s6 text-center text-sm text-ink-quiet">
              No tracks in {selectedKey}
              {bpmEnabled ? ` between ${bpmMin}–${bpmMax} BPM` : ''}.
            </div>
          ) : (
            <>
              <div className="flex flex-col">
                {visibleTracks.map(track => (
                  <div
                    key={track.id}
                    className="group relative grid grid-cols-[82px_minmax(0,1fr)_28px] items-baseline gap-[18px]
                               border-b border-hairline py-[15px]"
                  >
                    <span className="font-display text-[26px] leading-none tabular-nums text-accent">
                      {track.bpm != null ? track.bpm.toFixed(1) : '—'}
                    </span>
                    <div className="flex min-w-0 flex-col gap-[2px]">
                      <button
                        onClick={() => navigate(`/results?id=${track.id}`)}
                        className="min-w-0 truncate rounded text-left text-md leading-tight text-ink
                                   transition-colors after:absolute after:inset-0 after:content-['']
                                   group-hover:text-accent"
                      >
                        {track.title}
                      </button>
                      <span className="truncate text-xs text-ink-quiet">
                        {track.artist}
                        {track.vocal_class ? ` · ${VOCAL_LABEL[track.vocal_class]}` : ''}
                      </span>
                    </div>
                    <div className="self-center justify-self-end">
                      <SpotifyButton artist={track.artist} title={track.title} />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-s3 text-sm italic text-ink-quiet">
                Sorted by tempo, so the next record is the one nearest where you are.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
