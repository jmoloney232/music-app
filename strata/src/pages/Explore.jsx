import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CAMELOT_TO_KEY, formatKey } from '../utils/camelot'
import SpotifyButton from '../components/SpotifyButton'

const API = '/api'
const PAGE_SIZE = 50

const VOCAL_LABEL = {
  instrumental: 'Instrumental',
  vocal:        'Vocal',
  ambiguous:    'Mixed',
}

const VOCAL_COLOR = {
  instrumental: 'text-sky-400',
  vocal:        'text-pink-400',
  ambiguous:    'text-yellow-400',
}

// 1A, 1B, 2A, 2B, ..., 12A, 12B
const KEY_OPTIONS = Object.entries(CAMELOT_TO_KEY).sort(([a], [b]) => {
  const na = parseInt(a), nb = parseInt(b)
  return na !== nb ? na - nb : a.slice(-1).localeCompare(b.slice(-1))
})

function Tag({ children, color = 'text-text-secondary' }) {
  return (
    <span className={`text-xs font-mono border border-border rounded px-1.5 py-0.5 whitespace-nowrap ${color}`}>
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
      <span className="font-mono text-xs text-border w-6 text-right flex-shrink-0">{rank}</span>
      <div className="flex-1 min-w-0">
        <div className="font-body text-sm font-medium text-text-primary group-hover:text-white transition-colors truncate">
          {track.title}
        </div>
        <div className="font-body text-xs text-text-secondary truncate mt-0.5">{track.artist}</div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className="flex gap-1.5 flex-wrap justify-end max-w-[260px]">
          {track.bpm    && <Tag>{track.bpm} BPM</Tag>}
          {track.camelot && <Tag>{formatKey(track.camelot)}</Tag>}
          {track.vocal_class && (
            <Tag color={VOCAL_COLOR[track.vocal_class]}>
              {VOCAL_LABEL[track.vocal_class]}
            </Tag>
          )}
          {(track.styles ?? []).slice(0, 2).map(s => <Tag key={s}>{s}</Tag>)}
        </div>
        <SpotifyButton artist={track.artist} title={track.title} />
      </div>
    </button>
  )
}

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
    setTracks([])
    setTotal(0)
    setLoading(true)
    fetch(`${API}/explore/tracks?${buildParams(selectedCluster, fetchBpm, camelot, vocalType, 0)}`)
      .then(r => r.json())
      .then(d => { setTracks(d.tracks); setTotal(d.total) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [selectedCluster, fetchBpm, camelot, vocalType])

  const handleShowMore = () => {
    setLoadingMore(true)
    fetch(`${API}/explore/tracks?${buildParams(selectedCluster, fetchBpm, camelot, vocalType, tracks.length)}`)
      .then(r => r.json())
      .then(d => { setTracks(prev => [...prev, ...d.tracks]); setTotal(d.total) })
      .catch(() => {})
      .finally(() => setLoadingMore(false))
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
    <div className="min-h-[calc(100vh-80px)] bg-background px-6 py-10">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <h1 className="font-headline font-bold text-3xl text-text-primary tracking-wide">
            EXPLORE
          </h1>
          <p className="text-text-secondary font-body text-sm mt-1">
            Browse your catalog by genre, key, tempo, and more
          </p>
        </div>

        {/* Sound clusters */}
        {clusters.length > 0 && (
          <div className="mb-8">
            <div className="text-xs font-mono text-text-secondary uppercase tracking-widest mb-3">
              Sound Clusters
            </div>
            <p className="text-xs font-body text-text-secondary mb-3 opacity-70">
              Grouped by audio similarity — tracks in each cluster genuinely sound alike.
            </p>
            <div className="flex flex-wrap gap-2">
              {clusters.map(({ id, name, count }) => (
                <button
                  key={id}
                  onClick={() => setSelectedCluster(selectedCluster === id ? null : id)}
                  className={`text-sm px-3 py-1.5 rounded-full border font-body transition-colors ${
                    selectedCluster === id
                      ? 'bg-purple-primary border-purple-primary text-white'
                      : 'border-border text-text-secondary hover:border-purple-primary hover:text-text-primary'
                  }`}
                >
                  {name}
                  <span className="ml-1.5 font-mono text-xs opacity-60">{count}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Filter bar */}
        <div className="bg-surface border border-border rounded-lg px-5 py-4 mb-6">
          <div className="flex flex-wrap gap-6 items-start">

            {/* BPM */}
            <div className="flex-1 min-w-[200px]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono text-text-secondary uppercase tracking-widest">BPM</span>
                <label className="flex items-center gap-1.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={bpmEnabled}
                    onChange={e => setBpmEnabled(e.target.checked)}
                    style={{ accentColor: '#7B2FBE' }}
                    className="w-3 h-3"
                  />
                  <span className="text-xs font-mono text-text-secondary">Enable</span>
                </label>
              </div>
              <div className={`flex items-center gap-2 transition-opacity ${bpmEnabled ? 'opacity-100' : 'opacity-35 pointer-events-none'}`}>
                <span className="font-mono text-xs text-text-primary w-7 text-right tabular-nums">{bpmMin}</span>
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
                <span className="font-mono text-xs text-text-primary w-7 tabular-nums">{bpmMax}</span>
              </div>
            </div>

            {/* Key */}
            <div>
              <div className="text-xs font-mono text-text-secondary uppercase tracking-widest mb-2">Key</div>
              <select
                value={camelot}
                onChange={e => setCamelot(e.target.value)}
                className="bg-background border border-border rounded px-3 py-1.5 text-xs font-mono
                           text-text-primary focus:border-purple-primary outline-none cursor-pointer"
              >
                <option value="">Any Key</option>
                {KEY_OPTIONS.map(([key, standard]) => (
                  <option key={key} value={key}>{key} / {standard}</option>
                ))}
              </select>
            </div>

            {/* Vocal type */}
            <div>
              <div className="text-xs font-mono text-text-secondary uppercase tracking-widest mb-2">Type</div>
              <div className="flex gap-1">
                {[['', 'All'], ['vocal', 'Vocal'], ['instrumental', 'Instrumental'], ['ambiguous', 'Mixed']].map(([val, label]) => (
                  <button
                    key={val}
                    onClick={() => setVocalType(val)}
                    className={`text-xs px-3 py-1 rounded font-mono transition-colors ${
                      vocalType === val
                        ? 'bg-purple-primary text-white'
                        : 'border border-border text-text-secondary hover:text-text-primary'
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
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs font-mono text-text-secondary">
            {loading ? '…' : `${total.toLocaleString()} track${total !== 1 ? 's' : ''}`}
          </span>
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="text-xs font-mono text-text-secondary hover:text-purple-light transition-colors"
            >
              Clear all filters
            </button>
          )}
        </div>

        {/* Track list */}
        {loading ? (
          <div className="flex flex-col items-center gap-3 py-20">
            <div className="w-6 h-6 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
            {slowLoad && (
              <p className="text-text-secondary font-body text-sm animate-pulse">
                Waking up the server — first load can take up to 30s…
              </p>
            )}
          </div>
        ) : tracks.length === 0 ? (
          <div className="text-center py-20 text-text-secondary font-body text-sm">
            No tracks match the current filters.
          </div>
        ) : (
          <>
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

            {tracks.length < total && (
              <button
                onClick={handleShowMore}
                disabled={loadingMore}
                className="w-full mt-4 py-3 border border-border rounded-lg text-text-secondary
                           hover:border-purple-primary hover:text-text-primary font-body text-sm
                           transition-colors disabled:opacity-50"
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
