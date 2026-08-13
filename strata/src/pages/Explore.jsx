import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CAMELOT_TO_KEY } from '../utils/camelot'
import TrackRow from '../components/TrackRow'

function SkeletonRow({ delay = 0 }) {
  return (
    <div
      className="flex items-center gap-s3 rounded border border-hairline bg-surface px-s3 py-2.5"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="skeleton h-3 w-6 flex-shrink-0 rounded" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="skeleton h-3 w-2/5 rounded" />
        <div className="skeleton h-2.5 w-1/4 rounded" />
      </div>
      <div className="flex flex-shrink-0 gap-1.5">
        <div className="skeleton h-5 w-16 rounded" />
        <div className="skeleton h-5 w-20 rounded" />
        <div className="skeleton h-5 w-4 rounded" />
      </div>
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
    <div className="mx-auto max-w-dense px-s4 py-s5">
      <div>

        <div className="mb-s5">
          <h1 className="text-xl font-semibold text-ink">Explore the catalogue</h1>
          <p className="mt-1 text-sm text-ink-quiet">
            Narrow by tempo, key, vocal type, or the clusters the embeddings found.
          </p>
        </div>

        {/* Sound clusters */}
        {clusters.length > 0 && (
          <div className="mb-s5">
            <div className="mb-1.5 text-xs uppercase tracking-[0.16em] text-ink-quiet">
              Sound clusters
            </div>
            <p className="mb-s3 text-xs text-ink-quiet">
              Grouped by audio similarity — tracks in each cluster genuinely sound alike.
            </p>
            <div className="flex flex-wrap gap-s2">
              {clusters.map(({ id, name, count }) => (
                <button
                  key={id}
                  onClick={() => setSelectedCluster(selectedCluster === id ? null : id)}
                  aria-pressed={selectedCluster === id}
                  className={`h-control-sm rounded border px-s3 text-sm transition-colors ${
                    selectedCluster === id
                      ? 'border-accent bg-accent font-medium text-white'
                      : 'border-hairline text-ink-quiet hover:border-line-strong hover:bg-sunken hover:text-ink'
                  }`}
                >
                  {name}
                  <span className="ml-1.5 font-mono text-xs tabular-nums opacity-80">{count}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Filter bar */}
        <div className="mb-s4 border-y border-hairline bg-sunken px-s3 py-s3">
          <div className="flex flex-wrap items-start gap-s4">

            <div className="min-w-[200px] flex-1">
              <div className="mb-s2 flex items-center justify-between">
                <span className="text-xs uppercase tracking-[0.16em] text-ink-quiet">BPM</span>
                <label className="flex cursor-pointer select-none items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={bpmEnabled}
                    onChange={e => setBpmEnabled(e.target.checked)}
                    className="h-3 w-3"
                  />
                  <span className="text-xs text-ink-quiet">Enable</span>
                </label>
              </div>
              <div className={`flex items-center gap-s2 transition-opacity ${bpmEnabled ? 'opacity-100' : 'pointer-events-none opacity-40'}`}>
                <span className="w-7 text-right font-mono text-xs tabular-nums text-ink">{bpmMin}</span>
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
                <span className="w-7 font-mono text-xs tabular-nums text-ink">{bpmMax}</span>
              </div>
            </div>

            <div>
              <label htmlFor="key-filter" className="mb-s2 block text-xs uppercase tracking-[0.16em] text-ink-quiet">
                Key
              </label>
              <select
                id="key-filter"
                value={camelot}
                onChange={e => setCamelot(e.target.value)}
                className="h-control-sm cursor-pointer rounded border border-line-control bg-surface px-s2
                           font-mono text-xs text-ink outline-none focus:border-accent"
              >
                <option value="">Any key</option>
                {KEY_OPTIONS.map(([key, standard]) => (
                  <option key={key} value={key}>{key} / {standard}</option>
                ))}
              </select>
            </div>

            <div>
              <div className="mb-s2 text-xs uppercase tracking-[0.16em] text-ink-quiet">Type</div>
              <div className="flex flex-wrap gap-1">
                {[['', 'All'], ['vocal', 'Vocal'], ['instrumental', 'Instrumental'], ['ambiguous', 'Mixed']].map(([val, label]) => (
                  <button
                    key={val}
                    onClick={() => setVocalType(val)}
                    aria-pressed={vocalType === val}
                    className={`h-control-sm rounded border px-s2 text-xs transition-colors ${
                      vocalType === val
                        ? 'border-accent bg-accent font-medium text-white'
                        : 'border-hairline text-ink-quiet hover:border-line-strong hover:bg-surface hover:text-ink'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Count + clear */}
        <div className="mb-s4 flex items-center justify-between">
          <span className="font-mono text-xs tabular-nums text-ink-quiet">
            {loading ? '…' : `${total.toLocaleString()} track${total !== 1 ? 's' : ''}`}
          </span>
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="rounded text-xs text-ink-quiet transition-colors hover:text-accent"
            >
              Clear all filters
            </button>
          )}
        </div>

        {/* Track list */}
        {loading ? (
          <div className="flex flex-col gap-s2">
            {Array.from({ length: 10 }).map((_, i) => (
              <SkeletonRow key={i} delay={i * 35} />
            ))}
            {slowLoad && (
              <p className="mt-s3 text-center text-sm text-ink-quiet">
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
            <div className="flex flex-col gap-s2">
              {tracks.map((track, i) => (
                <TrackRow
                  key={track.id}
                  track={track}
                  rank={i + 1}
                  onClick={() => navigate(`/results?id=${track.id}`)}
                  showStyles
                />
              ))}
            </div>

            {tracks.length < total && (
              <button
                onClick={handleShowMore}
                disabled={loadingMore}
                className="mt-s3 h-control w-full rounded border border-line-control text-sm text-ink-quiet
                           transition-colors hover:bg-sunken hover:text-ink disabled:opacity-50"
              >
                {loadingMore
                  ? 'Loading…'
                  : `Show more (${(total - tracks.length).toLocaleString()} remaining)`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
