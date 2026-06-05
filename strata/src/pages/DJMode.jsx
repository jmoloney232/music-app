import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CAMELOT_TO_KEY, formatKey } from '../utils/camelot'
import SpotifyButton from '../components/SpotifyButton'

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

function segFill(pos, ring, active) {
  const h = ((pos - 1) * 30) % 360
  if (active) return `hsl(${h},82%,60%)`
  return ring === 'B' ? `hsl(${h},60%,36%)` : `hsl(${h},54%,27%)`
}

function CamelotWheel({ selected, onSelect }) {
  const segs = []

  for (let pos = 1; pos <= 12; pos++) {
    const startDeg = (pos - 1) * 30
    const endDeg = pos * 30
    const midDeg = startDeg + 15

    // Inner A ring (minor)
    const aKey = `${pos}A`
    const aActive = selected === aKey
    const [axL, ayL] = polar((A_INNER + A_OUTER) / 2, midDeg)
    segs.push(
      <g key={aKey} onClick={() => onSelect(aActive ? null : aKey)} style={{ cursor: 'pointer' }}>
        <path
          d={ringSegPath(A_INNER + 1, A_OUTER - 1, startDeg, endDeg)}
          fill={segFill(pos, 'A', aActive)}
          stroke={aActive ? 'rgba(255,255,255,0.9)' : 'none'}
          strokeWidth="1.5"
        />
        <text
          x={axL} y={ayL}
          textAnchor="middle" dominantBaseline="central"
          fontSize="9.5" fontFamily="JetBrains Mono, monospace"
          fontWeight={aActive ? 'bold' : 'normal'}
          fill={aActive ? 'white' : 'rgba(255,255,255,0.72)'}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {aKey}
        </text>
      </g>
    )

    // Outer B ring (major)
    const bKey = `${pos}B`
    const bActive = selected === bKey
    const [bxL, byL] = polar((B_INNER + B_OUTER) / 2, midDeg)
    segs.push(
      <g key={bKey} onClick={() => onSelect(bActive ? null : bKey)} style={{ cursor: 'pointer' }}>
        <path
          d={ringSegPath(B_INNER + 1, B_OUTER - 1, startDeg, endDeg)}
          fill={segFill(pos, 'B', bActive)}
          stroke={bActive ? 'rgba(255,255,255,0.9)' : 'none'}
          strokeWidth="1.5"
        />
        <text
          x={bxL} y={byL}
          textAnchor="middle" dominantBaseline="central"
          fontSize="9.5" fontFamily="JetBrains Mono, monospace"
          fontWeight={bActive ? 'bold' : 'normal'}
          fill={bActive ? 'white' : 'rgba(255,255,255,0.72)'}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {bKey}
        </text>
      </g>
    )
  }

  return (
    <svg viewBox="0 0 400 400" className="w-full max-w-[380px]">
      <circle cx={CX} cy={CY} r={B_OUTER + 10} fill="#141414" />
      {segs}
      {/* Center hole */}
      <circle cx={CX} cy={CY} r={A_INNER - 1} fill="#0A0A0A" />
      {selected ? (
        <>
          <text
            x={CX} y={CY - 9}
            textAnchor="middle" dominantBaseline="central"
            fontSize="20" fontWeight="bold"
            fontFamily="JetBrains Mono, monospace" fill="white"
          >
            {selected}
          </text>
          <text
            x={CX} y={CY + 13}
            textAnchor="middle" dominantBaseline="central"
            fontSize="9" fontFamily="Inter, sans-serif" fill="#A0A0A0"
          >
            {CAMELOT_TO_KEY[selected]}
          </text>
        </>
      ) : (
        <text
          x={CX} y={CY}
          textAnchor="middle" dominantBaseline="central"
          fontSize="9" fontFamily="Inter, sans-serif" fill="#444"
        >
          select a key
        </text>
      )}
    </svg>
  )
}

function Tag({ children }) {
  return (
    <span className="text-xs font-mono border border-border rounded px-1.5 py-0.5 text-text-secondary whitespace-nowrap">
      {children}
    </span>
  )
}

function TrackRow({ track, rank, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-surface border border-border rounded-lg px-4 py-3
                 hover:border-purple-primary transition-colors group flex items-center gap-3"
    >
      <span className="font-mono text-xs text-border w-5 text-right flex-shrink-0">{rank}</span>
      <div className="flex-1 min-w-0">
        <div className="font-body text-sm font-medium text-text-primary group-hover:text-white transition-colors truncate">
          {track.title}
        </div>
        <div className="font-body text-xs text-text-secondary truncate mt-0.5">{track.artist}</div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className="flex gap-1.5">
          {track.bpm && <Tag>{track.bpm} BPM</Tag>}
          {track.camelot && <Tag>{formatKey(track.camelot)}</Tag>}
        </div>
        <SpotifyButton artist={track.artist} title={track.title} />
      </div>
    </button>
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
    setLoading(true)
    let url = `${API}/tracks/by-key?camelot=${selectedKey}`
    if (fetchParams.enabled) url += `&bpm_min=${fetchParams.min}&bpm_max=${fetchParams.max}`
    fetch(url)
      .then(r => r.json())
      .then(setTracks)
      .catch(() => setTracks([]))
      .finally(() => setLoading(false))
  }, [selectedKey, fetchParams])

  return (
    <div className="min-h-[calc(100vh-80px)] bg-background px-6 py-10">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="font-headline font-bold text-3xl text-text-primary tracking-wide">
              DJ MODE
            </h1>
            <p className="text-text-secondary font-body text-sm mt-1">
              Click a key to browse your catalog by harmonic key
            </p>
          </div>
          <button
            onClick={() => navigate('/')}
            className="text-text-secondary hover:text-text-primary font-body text-sm flex items-center gap-1.5 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Back to search
          </button>
        </div>

        <div className="flex gap-10 items-start">

          {/* Left: Camelot wheel */}
          <div className="flex-shrink-0 w-[380px]">
            <CamelotWheel selected={selectedKey} onSelect={setSelectedKey} />
            <div className="flex justify-center gap-6 mt-2">
              <span className="text-xs font-mono text-text-secondary">Inner (A) = minor</span>
              <span className="text-xs font-mono text-text-secondary">Outer (B) = major</span>
            </div>
          </div>

          {/* Right: BPM filter + track list */}
          <div className="flex-1 min-w-0">

            {/* BPM filter */}
            <div className="bg-surface border border-border rounded-lg px-5 py-4 mb-6">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-mono text-text-secondary uppercase tracking-widest">
                  BPM Range
                </span>
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={bpmEnabled}
                    onChange={e => setBpmEnabled(e.target.checked)}
                    style={{ accentColor: '#7B2FBE' }}
                    className="w-3.5 h-3.5"
                  />
                  <span className="text-xs font-mono text-text-secondary">Enable filter</span>
                </label>
              </div>
              <div className={`flex items-center gap-3 transition-opacity ${bpmEnabled ? 'opacity-100' : 'opacity-35 pointer-events-none'}`}>
                <span className="font-mono text-sm text-text-primary w-8 text-right tabular-nums">
                  {bpmMin}
                </span>
                <input
                  type="range" min={60} max={215} value={bpmMin}
                  onChange={e => setBpmMin(Math.min(+e.target.value, bpmMax - 5))}
                  className="flex-1" style={{ accentColor: '#7B2FBE' }}
                />
                <span className="text-xs text-text-secondary">–</span>
                <input
                  type="range" min={65} max={220} value={bpmMax}
                  onChange={e => setBpmMax(Math.max(+e.target.value, bpmMin + 5))}
                  className="flex-1" style={{ accentColor: '#7B2FBE' }}
                />
                <span className="font-mono text-sm text-text-primary w-8 tabular-nums">
                  {bpmMax}
                </span>
              </div>
            </div>

            {/* Track list */}
            {!selectedKey ? (
              <div className="text-center py-24 text-text-secondary font-body text-sm">
                ← Click a key on the wheel to see matching tracks
              </div>
            ) : loading ? (
              <div className="flex flex-col items-center gap-3 py-24">
                <div className="w-6 h-6 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
                {slowLoad && (
                  <p className="text-text-secondary font-body text-sm animate-pulse">
                    Waking up the server — first load can take up to 30s…
                  </p>
                )}
              </div>
            ) : tracks.length === 0 ? (
              <div className="text-center py-24 text-text-secondary font-body text-sm">
                No tracks found in {formatKey(selectedKey)}
                {bpmEnabled ? ` between ${bpmMin}–${bpmMax} BPM` : ''}.
              </div>
            ) : (
              <>
                <div className="text-xs font-mono text-text-secondary mb-3">
                  {tracks.length} {tracks.length === 1 ? 'track' : 'tracks'} in{' '}
                  <span className="text-text-primary">{formatKey(selectedKey)}</span>
                  {bpmEnabled && (
                    <span> · {bpmMin}–{bpmMax} BPM</span>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  {tracks.map((track, i) => (
                    <TrackRow
                      key={track.id}
                      track={track}
                      rank={i + 1}
                      onClick={() => navigate(`/results?id=${track.id}`)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
