import { useEffect, useState, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { formatKey, compatibleKeys } from '../utils/camelot'
import SpotifyButton from '../components/SpotifyButton'
import Tag from '../components/Tag'

function cleanStyle(s) {
  const parts = s.split('---')
  return parts[parts.length - 1].trim()
}

const API = '/api'

const VOCAL_LABEL = {
  instrumental: 'Instrumental',
  vocal:        'Vocal',
  ambiguous:    'Mixed',
}

const VOCAL_COLOR = {
  instrumental: 'text-sky-400 border-sky-400/30',
  vocal:        'text-pink-400 border-pink-400/30',
  ambiguous:    'text-yellow-400 border-yellow-400/30',
}

function ScoreBar({ score }) {
  const pct = Math.round(score * 100)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    setWidth(0)
    const t = setTimeout(() => setWidth(pct), 60)
    return () => clearTimeout(t)
  }, [pct])

  const barColor =
    pct >= 80 ? 'linear-gradient(90deg,#16a34a,#22c55e)' :
    pct >= 60 ? 'linear-gradient(90deg,#d97706,#f59e0b)' :
                'linear-gradient(90deg,#404040,#606060)'

  const pctColor =
    pct >= 80 ? 'text-success' :
    pct >= 60 ? 'text-warning' :
                'text-text-subtle'

  return (
    <div className="flex items-center gap-2 min-w-[96px]">
      <div className="flex-1 h-2 bg-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${width}%`,
            transition: 'width 0.55s cubic-bezier(0.4,0,0.2,1)',
            background: barColor,
          }}
        />
      </div>
      <span className={`font-mono text-xs w-10 text-right tabular-nums ${pctColor}`}>{pct}%</span>
    </div>
  )
}


function TrackCard({ track, rank, index = 0, onClick }) {
  const pct = Math.round(track.score * 100)
  const accent =
    pct >= 80 ? 'bg-success' :
    pct >= 60 ? 'bg-warning' :
    'bg-border'

  return (
    <button
      onClick={onClick}
      className="relative w-full text-left bg-surface border border-border rounded-lg px-5 py-4
                 hover:border-purple-primary hover:shadow-[0_0_0_1px_rgba(123,47,190,0.3),0_4px_24px_rgba(123,47,190,0.12)]
                 transition-all duration-200 group animate-fade-up overflow-hidden"
      style={{ animationDelay: `${Math.min(index * 35, 350)}ms` }}
    >
      <div className={`absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full ${accent}`} />
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4 min-w-0">
          <span className="font-mono text-xs text-border pt-1 w-5 flex-shrink-0 text-right">
            {rank}
          </span>
          <div className="min-w-0">
            <div className="font-body font-medium text-text-primary group-hover:text-white transition-colors truncate">
              {track.title}
            </div>
            <div className="font-body text-text-secondary text-sm truncate mt-0.5">
              {track.artist}
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {track.bpm && (
                <Tag color="text-sky-400 border-sky-400/30">{track.bpm} BPM</Tag>
              )}
              {track.camelot && (
                <Tag color="text-emerald-400 border-emerald-400/30">{formatKey(track.camelot)}</Tag>
              )}
              {track.vocal_class && (
                <Tag color={VOCAL_COLOR[track.vocal_class]}>
                  {VOCAL_LABEL[track.vocal_class] ?? track.vocal_class}
                </Tag>
              )}
              {(track.styles ?? []).slice(0, 2).map(s => (
                <Tag key={s}>{cleanStyle(s)}</Tag>
              ))}
            </div>
          </div>
        </div>
        <div className="flex-shrink-0 pt-1 flex items-center gap-2">
          <SpotifyButton artist={track.artist} title={track.title} />
          <ScoreBar score={track.score} />
        </div>
      </div>
    </button>
  )
}

function QueryCard({ track }) {
  return (
    <div className="relative bg-surface border border-purple-primary/60 rounded-xl px-7 py-6 mb-8 overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at top left, rgba(123,47,190,0.25) 0%, transparent 65%)' }}
      />
      <div className="relative">
        <div className="flex items-start justify-between gap-4">
          <div className="text-xs font-body text-purple-light uppercase tracking-widest mb-3">
            Query Track
          </div>
          <SpotifyButton artist={track.artist} title={track.title} />
        </div>
        <div className="font-headline font-bold text-3xl text-text-primary leading-tight">{track.title}</div>
        <div className="font-body text-text-secondary text-lg mt-1">{track.artist}</div>
        <div className="flex flex-wrap gap-2 mt-3">
          {track.bpm && (
            <Tag color="text-sky-400 border-sky-400/30">{track.bpm} BPM</Tag>
          )}
          {track.camelot && (
            <Tag color="text-emerald-400 border-emerald-400/30">{formatKey(track.camelot)}</Tag>
          )}
          {track.vocal_class && (
            <Tag color={VOCAL_COLOR[track.vocal_class]}>
              {VOCAL_LABEL[track.vocal_class] ?? track.vocal_class}
            </Tag>
          )}
          {(track.styles ?? []).slice(0, 3).map(s => (
            <Tag key={s}>{cleanStyle(s)}</Tag>
          ))}
        </div>
      </div>
    </div>
  )
}

function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-3 py-1 rounded font-body transition-all duration-150 ${
        active
          ? 'bg-purple-primary text-white shadow-[0_0_12px_rgba(123,47,190,0.4)]'
          : 'bg-surface border border-border text-text-secondary hover:text-text-primary hover:border-[#404040]'
      }`}
    >
      {children}
    </button>
  )
}

export default function Results() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const trackId = params.get('id')

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [keyFilter, setKeyFilter] = useState('all')
  const [bpmFilter, setBpmFilter] = useState(false)
  const [displayLimit, setDisplayLimit] = useState(15)

  useEffect(() => {
    if (!trackId) {
      setError('No track selected.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    setKeyFilter('all')
    setBpmFilter(false)
    setDisplayLimit(15)
    fetch(`${API}/similar/${trackId}?top=100`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [trackId])

  const filteredResults = useMemo(() => {
    if (!data) return []
    let results = data.results

    if (keyFilter === 'compatible') {
      const compat = new Set(compatibleKeys(data.query.camelot))
      results = results.filter(t => compat.has(t.camelot))
    } else if (keyFilter === 'exact') {
      results = results.filter(t => t.camelot === data.query.camelot)
    }

    if (bpmFilter && data.query.bpm) {
      const lo = data.query.bpm * 0.94
      const hi = data.query.bpm * 1.06
      results = results.filter(t => t.bpm != null && t.bpm >= lo && t.bpm <= hi)
    }

    if (keyFilter === 'all' && !bpmFilter) return results.slice(0, displayLimit)

    return results
  }, [data, keyFilter, bpmFilter, displayLimit])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-80px)] bg-background gap-4">
        <div className="relative w-10 h-10">
          <div className="absolute inset-0 border-2 border-purple-primary/20 rounded-full" />
          <div className="absolute inset-0 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
        </div>
        <p className="text-text-secondary font-body text-sm animate-pulse">Finding similar tracks…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-80px)] bg-background gap-4">
        <p className="text-text-secondary font-body">{error}</p>
        <button
          onClick={() => navigate('/')}
          className="text-purple-light font-body text-sm hover:text-white transition-colors"
        >
          ← Back to search
        </button>
      </div>
    )
  }

  const filtersActive = keyFilter !== 'all' || bpmFilter

  return (
    <div className="min-h-[calc(100vh-80px)] bg-background px-6 py-12 max-w-2xl mx-auto">
      {/* Back link */}
      <button
        onClick={() => navigate('/')}
        className="text-text-secondary hover:text-text-primary font-body text-sm mb-8 flex items-center gap-1.5 transition-colors group"
      >
        <svg
          className="w-4 h-4 transition-transform duration-150 group-hover:-translate-x-0.5"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to search
      </button>

      {/* Query card */}
      <QueryCard track={data.query} />

      {/* Stats row */}
      <div className="flex gap-6 mb-5 font-mono text-xs text-text-secondary">
        <span>{data.total_compared} tracks compared</span>
        <span>High <span className="text-text-primary">{Math.round(data.highest * 100)}%</span></span>
        <span>Med <span className="text-text-primary">{Math.round(data.median * 100)}%</span></span>
        <span>Low <span className="text-text-primary">{Math.round(data.lowest * 100)}%</span></span>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 py-3 mb-5 border-t border-b border-border">
        <span className="text-xs font-body text-text-secondary uppercase tracking-widest mr-1">
          Filter
        </span>
        <FilterPill active={keyFilter === 'all'} onClick={() => setKeyFilter('all')}>
          All
        </FilterPill>
        <FilterPill active={keyFilter === 'compatible'} onClick={() => setKeyFilter('compatible')}>
          Compatible Keys
        </FilterPill>
        <FilterPill active={keyFilter === 'exact'} onClick={() => setKeyFilter('exact')}>
          Exact Key
        </FilterPill>
        {data.query.bpm && (
          <FilterPill active={bpmFilter} onClick={() => setBpmFilter(v => !v)}>
            BPM ±6%
          </FilterPill>
        )}
        {filtersActive && (
          <span className="text-xs font-mono text-text-secondary ml-auto">
            {filteredResults.length} of {data.results.length} shown
          </span>
        )}
      </div>

      {/* Results */}
      <div className="flex flex-col gap-2">
        {filteredResults.length === 0 ? (
          <div className="text-center py-10 text-text-secondary font-body text-sm">
            No results match the current filter.{' '}
            <button
              onClick={() => { setKeyFilter('all'); setBpmFilter(false) }}
              className="text-purple-light hover:text-white transition-colors"
            >
              Clear filters
            </button>
          </div>
        ) : (
          filteredResults.map((track, i) => (
            <TrackCard
              key={track.id}
              track={track}
              rank={i + 1}
              index={i}
              onClick={() => navigate(`/results?id=${track.id}`)}
            />
          ))
        )}
      </div>

      {/* Show more */}
      {keyFilter === 'all' && !bpmFilter && data && displayLimit < data.results.length && (
        <button
          onClick={() => setDisplayLimit(n => n + 15)}
          className="w-full mt-4 py-3 border border-border rounded-lg text-text-secondary
                     hover:border-purple-primary hover:text-text-primary hover:shadow-[0_0_16px_rgba(123,47,190,0.1)]
                     font-body text-sm transition-all duration-200"
        >
          Show more ({data.results.length - displayLimit} remaining)
        </button>
      )}
    </div>
  )
}
