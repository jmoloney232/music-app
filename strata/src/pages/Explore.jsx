import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CAMELOT_TO_KEY } from '../utils/camelot'
import TrackRow from '../components/TrackRow'

/* Skeletons hold the table's column tracks so nothing shifts when data lands. */
function SkeletonRow({ opacity = 1 }) {
  return (
    <div
      className="grid grid-cols-[minmax(0,1fr)_28px] items-center gap-x-s4 border-b border-hairline py-[15px]
                 md:grid-cols-[minmax(0,1fr)_92px_130px_116px_140px_28px]"
      style={{ opacity }}
    >
      <div className="skeleton h-[15px] max-w-[280px] rounded-chip" />
      <div className="hidden h-[15px] rounded-chip bg-tan md:block" />
      <div className="hidden h-[15px] rounded-chip bg-tan md:block" />
      <div className="hidden h-[15px] rounded-chip bg-tan md:block" />
      <div className="hidden h-[15px] rounded-chip bg-tan md:block" />
      <span />
    </div>
  )
}

const API = '/api'
const PAGE_SIZE = 50

// 1A, 1B, 2A, 2B, ..., 12A, 12B
const KEY_OPTIONS = Object.entries(CAMELOT_TO_KEY).sort(([a], [b]) => {
  const na = parseInt(a), nb = parseInt(b)
  return na !== nb ? na - nb : a.slice(-1).localeCompare(b.slice(-1))
})

function buildParams(selectedCluster, fetchBpm, camelot, vocalType, offset) {
  const p = new URLSearchParams({ limit: PAGE_SIZE, offset })
  if (selectedCluster !== null) p.set('cluster_id', selectedCluster)
  if (fetchBpm.enabled)         { p.set('bpm_min', fetchBpm.min); p.set('bpm_max', fetchBpm.max) }
  if (camelot)                  p.set('camelot', camelot)
  if (vocalType)                p.set('vocal', vocalType)
  return p.toString()
}

export default function Explore() {
  const navigate = useNavigate()

  // Cluster chips
  const [clusters, setClusters] = useState([])
  const [selectedCluster, setSelectedCluster] = useState(null)

  // Filters
  const [bpmEnabled, setBpmEnabled] = useState(false)
  const [bpmMin, setBpmMin] = useState(60)
  const [bpmMax, setBpmMax] = useState(220)
  const [camelot, setCamelot] = useState('')
  const [vocalType, setVocalType] = useState('')

  // Debounced BPM
  const [fetchBpm, setFetchBpm] = useState({ enabled: false, min: 60, max: 220 })
  useEffect(() => {
    const t = setTimeout(() => setFetchBpm({ enabled: bpmEnabled, min: bpmMin, max: bpmMax }), 300)
    return () => clearTimeout(t)
  }, [bpmEnabled, bpmMin, bpmMax])

  // Track list
  const [tracks, setTracks] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
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

  // Load cluster chips once
  useEffect(() => {
    fetch(`${API}/explore/clusters`)
      .then(r => r.json())
      .then(setClusters)
      .catch(() => {})
  }, [])

  // Reload track list when any filter changes
  useEffect(() => {
    // Filters change faster than the catalogue responds; without a sequence
    // guard a stale response can repopulate the list under the current filters.
    const requestId = ++latestRequest.current
    setTracks([])
    setTotal(0)
    setLoading(true)
    fetch(`${API}/explore/tracks?${buildParams(selectedCluster, fetchBpm, camelot, vocalType, 0)}`)
      .then(r => r.json())
      .then(d => {
        if (requestId !== latestRequest.current) return
        setTracks(d.tracks)
        setTotal(d.total)
      })
      .catch(() => {})
      .finally(() => { if (requestId === latestRequest.current) setLoading(false) })
  }, [selectedCluster, fetchBpm, camelot, vocalType])

  const handleShowMore = () => {
    const requestId = latestRequest.current
    setLoadingMore(true)
    fetch(`${API}/explore/tracks?${buildParams(selectedCluster, fetchBpm, camelot, vocalType, tracks.length)}`)
      .then(r => r.json())
      .then(d => {
        // A filter change mid-page-load invalidates this page entirely.
        if (requestId !== latestRequest.current) return
        setTracks(prev => [...prev, ...d.tracks])
        setTotal(d.total)
      })
      .catch(() => {})
      .finally(() => { if (requestId === latestRequest.current) setLoadingMore(false) })
  }

  const clearFilters = () => {
    setSelectedCluster(null)
    setBpmEnabled(false)
    setBpmMin(60)
    setBpmMax(220)
    setCamelot('')
    setVocalType('')
  }

  const hasFilters = selectedCluster !== null || bpmEnabled || camelot || vocalType

  return (
    <div className="mx-auto max-w-dense px-s4 pb-s6 pt-s5 sm:px-s6">

      {/* Title row */}
      <div className="mb-[30px] flex flex-wrap items-end justify-between gap-s4 border-b border-line-strong pb-s4">
        <h1 className="font-display text-[clamp(36px,6vw,56px)] font-light leading-none text-ink">
          The catalogue
        </h1>
        <span className="font-display text-[34px] leading-none tabular-nums text-ink">
          {loading ? '…' : total.toLocaleString()}{' '}
          <span className="font-sans text-base text-ink-quiet">tracks match</span>
        </span>
      </div>

      {/* Sound clusters */}
      {clusters.length > 0 && (
        <div className="mb-[30px] flex flex-wrap gap-[10px]">
          {clusters.map(({ id, name, count }) => (
            <button
              key={id}
              onClick={() => setSelectedCluster(selectedCluster === id ? null : id)}
              aria-pressed={selectedCluster === id}
              className={`rounded border px-4 py-2 text-sm tabular-nums transition-colors ${
                selectedCluster === id
                  ? 'border-accent text-accent'
                  : 'border-line-strong text-ink-soft hover:border-accent hover:text-accent'
              }`}
            >
              {name} · {count.toLocaleString()}
            </button>
          ))}
        </div>
      )}

      {/* Filter band */}
      <div className="mb-[30px] grid grid-cols-1 items-end gap-s5 border-y border-divider py-s4 lg:grid-cols-[1fr_240px_260px] lg:gap-[44px]">

        <div className="flex flex-col gap-s3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-[0.2em] text-ink-quiet">Tempo</span>
            <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-ink-quiet">
              <input
                type="checkbox"
                checked={bpmEnabled}
                onChange={e => setBpmEnabled(e.target.checked)}
                className="h-3 w-3"
              />
              Enable
            </label>
          </div>
          <div className={`flex flex-col gap-2 transition-opacity ${bpmEnabled ? 'opacity-100' : 'pointer-events-none opacity-40'}`}>
            <span className="font-display text-[24px] leading-none tabular-nums text-ink">
              {bpmMin} <span className="text-ink-muted">–</span> {bpmMax}
            </span>
            <div className="flex items-center gap-s3">
              <input
                type="range" min={60} max={215} value={bpmMin}
                aria-label="Minimum BPM"
                onChange={e => setBpmMin(Math.min(+e.target.value, bpmMax - 5))}
                className="flex-1"
              />
              <input
                type="range" min={65} max={220} value={bpmMax}
                aria-label="Maximum BPM"
                onChange={e => setBpmMax(Math.max(+e.target.value, bpmMin + 5))}
                className="flex-1"
              />
            </div>
            <div className="flex justify-between text-[11px] tabular-nums text-ink-muted">
              <span>60</span><span>220</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-s3">
          <label htmlFor="key-filter" className="text-[10px] uppercase tracking-[0.2em] text-ink-quiet">
            Key
          </label>
          <select
            id="key-filter"
            value={camelot}
            onChange={e => setCamelot(e.target.value)}
            className="cursor-pointer rounded border border-line-control bg-canvas px-[14px] py-[10px]
                       text-sm text-ink-soft outline-none focus:border-accent"
          >
            <option value="">All 24 keys</option>
            {KEY_OPTIONS.map(([key, standard]) => (
              <option key={key} value={key}>{key} / {standard}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-s3">
          <span className="text-[10px] uppercase tracking-[0.2em] text-ink-quiet">Vocal</span>
          <div className="flex gap-2">
            {[['', 'Any'], ['vocal', 'Vocal'], ['instrumental', 'Instr.'], ['ambiguous', 'Mixed']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setVocalType(val)}
                aria-pressed={vocalType === val}
                className={`flex-1 rounded border py-[9px] text-xs transition-colors ${
                  vocalType === val
                    ? 'border-accent text-accent'
                    : 'border-line-strong text-ink-soft hover:border-accent hover:text-accent'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {hasFilters && (
        <div className="mb-s4 flex justify-end">
          <button
            onClick={clearFilters}
            className="rounded border-b border-accent pb-[2px] text-xs uppercase tracking-[0.08em] text-accent
                       transition-colors hover:text-accent-deep"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Table */}
      <div className="hidden grid-cols-[minmax(0,1fr)_92px_130px_116px_140px_28px] gap-x-s4 border-b border-line-strong
                      pb-2 text-[10px] uppercase tracking-[0.18em] text-ink-muted md:grid">
        <span>Track</span><span>BPM</span><span>Key</span><span>Vocal</span><span>Style</span><span />
      </div>

      {loading ? (
        <div className="flex flex-col">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonRow key={i} opacity={Math.max(0.15, 1 - i * 0.12)} />
          ))}
          {slowLoad && (
            <p className="mt-s4 text-center text-sm italic text-ink-quiet">
              Waking up the server — first load can take up to 30s…
            </p>
          )}
        </div>
      ) : tracks.length === 0 ? (
        <div className="rounded border border-dashed border-line-strong px-s4 py-s6 text-center text-sm text-ink-quiet">
          No tracks match the current filters.
        </div>
      ) : (
        <>
          <div className="flex flex-col">
            {tracks.map(track => (
              <TrackRow
                key={track.id}
                track={track}
                onClick={() => navigate(`/results?id=${track.id}`)}
              />
            ))}
          </div>

          {tracks.length < total && (
            <div className="mt-s4 flex items-center gap-[18px]">
              <button
                onClick={handleShowMore}
                disabled={loadingMore}
                className="rounded border border-accent px-[22px] py-[9px] text-sm text-accent
                           transition-colors hover:bg-accent-fill disabled:opacity-50"
              >
                {loadingMore ? 'Loading…' : 'Next 50'}
              </button>
              <span className="text-xs tabular-nums text-ink-muted">
                {(total - tracks.length).toLocaleString()} remaining
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
