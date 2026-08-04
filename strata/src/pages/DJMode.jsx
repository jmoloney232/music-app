import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CAMELOT_TO_KEY, formatKey, keyColor } from '../utils/camelot'
import TrackRow from '../components/TrackRow'

const API = '/api'

// SVG wheel geometry
const CX = 200, CY = 200
const A_INNER = 56, A_OUTER = 112
const B_INNER = 116, B_OUTER = 178

function polar(r, deg) {
  const rad = (deg - 90) * Math.PI / 180
  return [+(CX + r * Math.cos(rad)).toFixed(2), +(CY + r * Math.sin(rad)).toFixed(2)]
}

function ringSegPath(innerR, outerR, startDeg, endDeg) {
  const GAP = 0.7
  const s = startDeg + GAP, e = endDeg - GAP
  const [x1i, y1i] = polar(innerR, s)
  const [x1o, y1o] = polar(outerR, s)
  const [x2o, y2o] = polar(outerR, e)
  const [x2i, y2i] = polar(innerR, e)
  return (
    `M${x1i} ${y1i} L${x1o} ${y1o} ` +
    `A${outerR} ${outerR} 0 0 1 ${x2o} ${y2o} ` +
    `L${x2i} ${y2i} ` +
    `A${innerR} ${innerR} 0 0 0 ${x1i} ${y1i}Z`
  )
}

function shortKey(camelot) {
  const full = CAMELOT_TO_KEY[camelot]
  if (!full) return ''
  const [note, type] = full.split(' ')
  return type === 'minor' ? `${note}m` : note
}

function Segment({ camelot, active, onSelect, innerR, outerR, startDeg, endDeg }) {
  const [lx, ly] = polar((innerR + outerR) / 2, startDeg + 15)
  const label = active ? '#FFFFFF' : '#1B1815'
  const standard = CAMELOT_TO_KEY[camelot]

  return (
    <g
      role="button"
      tabIndex={0}
      aria-pressed={active}
      aria-label={`${camelot}, ${standard}`}
      onClick={() => onSelect(active ? null : camelot)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(active ? null : camelot)
        }
      }}
      style={{ cursor: 'pointer' }}
    >
      <path
        d={ringSegPath(innerR + 1, outerR - 1, startDeg, endDeg)}
        fill={keyColor(camelot, active ? 'selected' : undefined)}
        stroke={active ? '#1B1815' : 'rgba(27,24,21,0.10)'}
        strokeWidth={active ? 1.5 : 0.75}
      />
      <text
        x={lx} y={ly - 5}
        textAnchor="middle" dominantBaseline="central"
        fontSize="9" fontFamily="'IBM Plex Mono', monospace"
        fontWeight={active ? 600 : 500}
        fill={label}
        style={{ pointerEvents: 'none', userSelect: 'none' }}
      >
        {camelot}
      </text>
      <text
        x={lx} y={ly + 7}
        textAnchor="middle" dominantBaseline="central"
        fontSize="7" fontFamily="'IBM Plex Mono', monospace"
        fill={label}
        opacity={active ? 0.9 : 0.7}
        style={{ pointerEvents: 'none', userSelect: 'none' }}
      >
        {shortKey(camelot)}
      </text>
    </g>
  )
}

function CamelotWheel({ selected, onSelect }) {
  const segs = []

  for (let pos = 1; pos <= 12; pos++) {
    const startDeg = (pos - 1) * 30
    const endDeg = pos * 30

    segs.push(
      <Segment
        key={`${pos}A`} camelot={`${pos}A`} active={selected === `${pos}A`}
        onSelect={onSelect} innerR={A_INNER} outerR={A_OUTER}
        startDeg={startDeg} endDeg={endDeg}
      />,
      <Segment
        key={`${pos}B`} camelot={`${pos}B`} active={selected === `${pos}B`}
        onSelect={onSelect} innerR={B_INNER} outerR={B_OUTER}
        startDeg={startDeg} endDeg={endDeg}
      />,
    )
  }

  return (
    <svg viewBox="0 0 400 400" className="w-full" role="group" aria-label="Camelot wheel">
      <circle cx={CX} cy={CY} r={B_OUTER + 10} fill="#FFFFFF" stroke="#E0CDB4" />
      {segs}
      <circle cx={CX} cy={CY} r={A_INNER - 1} fill="#FFFFFF" stroke="#E0CDB4" />
      {selected ? (
        <>
          <text
            x={CX} y={CY - 9}
            textAnchor="middle" dominantBaseline="central"
            fontSize="20" fontWeight="600"
            fontFamily="'IBM Plex Mono', monospace" fill="#1B1815"
          >
            {selected}
          </text>
          <text
            x={CX} y={CY + 13}
            textAnchor="middle" dominantBaseline="central"
            fontSize="9" fontFamily="'IBM Plex Sans', sans-serif" fill="#5C544B"
          >
            {CAMELOT_TO_KEY[selected]}
          </text>
        </>
      ) : (
        <text
          x={CX} y={CY}
          textAnchor="middle" dominantBaseline="central"
          fontSize="9" fontFamily="'IBM Plex Sans', sans-serif" fill="#695F55"
        >
          select a key
        </text>
      )}
    </svg>
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

  useEffect(() => {
    if (loading) {
      slowTimer.current = setTimeout(() => setSlowLoad(true), 4000)
    } else {
      clearTimeout(slowTimer.current)
      setSlowLoad(false)
    }
    return () => clearTimeout(slowTimer.current)
  }, [loading])

  // Debounce BPM slider changes so we don't fire on every tick
  const [fetchParams, setFetchParams] = useState({ min: 80, max: 160, enabled: false })
  useEffect(() => {
    const t = setTimeout(
      () => setFetchParams({ min: bpmMin, max: bpmMax, enabled: bpmEnabled }),
      300,
    )
    return () => clearTimeout(t)
  }, [bpmMin, bpmMax, bpmEnabled])

  useEffect(() => {
    if (!selectedKey) { setTracks([]); return }
    // The timer is debounced but the responses are not ordered — without this
    // a slow early request can land after a newer one and show the wrong key.
    const requestId = ++latestRequest.current
    setLoading(true)
    let url = `${API}/tracks/by-key?camelot=${selectedKey}`
    if (fetchParams.enabled) url += `&bpm_min=${fetchParams.min}&bpm_max=${fetchParams.max}`
    fetch(url)
      .then(r => r.json())
      .then(d => { if (requestId === latestRequest.current) setTracks(d) })
      .catch(() => { if (requestId === latestRequest.current) setTracks([]) })
      .finally(() => { if (requestId === latestRequest.current) setLoading(false) })
  }, [selectedKey, fetchParams])

  return (
    <div className="mx-auto max-w-dense px-s4 py-s5">
      <div className="mb-s5 flex flex-wrap items-start justify-between gap-s3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Browse by key</h1>
          <p className="mt-1 text-sm text-ink-quiet">
            Pick a key to see everything in your catalogue that sits in it.
          </p>
        </div>
        <button
          onClick={() => navigate('/')}
          className="rounded text-sm text-ink-quiet transition-colors hover:text-accent"
        >
          ← Back to search
        </button>
      </div>

      <div className="flex flex-col gap-s5 lg:flex-row lg:items-start lg:gap-s5">
        <div className="mx-auto w-full max-w-[380px] flex-shrink-0 lg:mx-0 lg:w-[380px]">
          <CamelotWheel selected={selectedKey} onSelect={setSelectedKey} />
          <div className="mt-s3 flex justify-center gap-s4 text-xs text-ink-quiet">
            <span>Inner ring = minor (A)</span>
            <span>Outer ring = major (B)</span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-s4 border-y border-hairline bg-sunken px-s3 py-s3">
            <div className="mb-s3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-[0.16em] text-ink-quiet">BPM range</span>
              <label className="flex cursor-pointer select-none items-center gap-s2">
                <input
                  type="checkbox"
                  checked={bpmEnabled}
                  onChange={e => setBpmEnabled(e.target.checked)}
                  className="h-3.5 w-3.5"
                />
                <span className="text-xs text-ink-quiet">Enable filter</span>
              </label>
            </div>
            <div
              className={`flex items-center gap-s3 transition-opacity ${
                bpmEnabled ? 'opacity-100' : 'pointer-events-none opacity-40'
              }`}
            >
              <span className="w-8 text-right font-mono text-sm tabular-nums text-ink">{bpmMin}</span>
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
              <span className="w-8 font-mono text-sm tabular-nums text-ink">{bpmMax}</span>
            </div>
          </div>

          {!selectedKey ? (
            <div className="rounded border border-dashed border-line-strong px-s4 py-s6 text-center">
              <p className="text-sm font-medium text-ink">No key selected</p>
              <p className="mx-auto mt-1 max-w-[260px] text-xs leading-relaxed text-ink-quiet">
                Click any segment on the wheel to browse your catalogue by harmonic key.
              </p>
            </div>
          ) : loading ? (
            <div className="flex flex-col items-center gap-s3 py-s6">
              <div
                role="status"
                className="h-6 w-6 animate-spin rounded-full border-2 border-line-strong border-t-accent"
              />
              {slowLoad && (
                <p className="text-sm text-ink-quiet">
                  Waking up the server — first load can take up to 30s…
                </p>
              )}
            </div>
          ) : tracks.length === 0 ? (
            <div className="py-s6 text-center text-sm text-ink-quiet">
              No tracks in {formatKey(selectedKey)}
              {bpmEnabled ? ` between ${bpmMin}–${bpmMax} BPM` : ''}.
            </div>
          ) : (
            <>
              <div className="mb-s3 font-mono text-xs tabular-nums text-ink-quiet">
                {tracks.length} {tracks.length === 1 ? 'track' : 'tracks'} in{' '}
                <span className="text-ink">{formatKey(selectedKey)}</span>
                {bpmEnabled && <span> · {bpmMin}–{bpmMax} BPM</span>}
              </div>
              <div className="flex flex-col gap-s2">
                {tracks.map((track, i) => (
                  <TrackRow
                    key={track.id}
                    track={track}
                    rank={i + 1}
                    showStyles
                    onClick={() => navigate(`/results?id=${track.id}`)}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
