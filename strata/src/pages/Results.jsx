import { useEffect, useState, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { formatKey, compatibleKeys } from '../utils/camelot'

const API = '/api'

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

function ScoreBar({ score }) {
  const pct = Math.round(score * 100)
  return (
    <div className="flex items-center gap-2 min-w-[96px]">
      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-purple-primary"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs text-purple-light w-10 text-right">{pct}%</span>
    </div>
  )
}

function Tag({ children, color = 'text-text-secondary' }) {
  return (
    <span className={`text-xs font-mono border border-border rounded px-1.5 py-0.5 ${color}`}>
      {children}
    </span>
  )
}

function TrackCard({ track, rank, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-surface border border-border rounded-lg px-5 py-4
                 hover:border-purple-primary transition-colors group"
    >
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
              {track.bpm && <Tag>{track.bpm} BPM</Tag>}
              {track.camelot && <Tag>{formatKey(track.camelot)}</Tag>}
              {track.vocal_class && (
                <Tag color={VOCAL_COLOR[track.vocal_class]}>
                  {VOCAL_LABEL[track.vocal_class] ?? track.vocal_class}
                </Tag>
              )}
              {(track.styles ?? []).slice(0, 2).map(s => (
                <Tag key={s}>{s}</Tag>
              ))}
            </div>
          </div>
        </div>
        <div className="flex-shrink-0 pt-1">
          <ScoreBar score={track.score} />
        </div>
      </div>
    </button>
  )
}

function QueryCard({ track }) {
  return (
    <div className="bg-surface border border-purple-primary rounded-lg px-6 py-5 mb-8">
      <div className="text-xs font-mono text-purple-light uppercase tracking-widest mb-2">
        Query Track
      </div>
      <div className="font-headline font-bold text-2xl text-text-primary">{track.title}</div>
      <div className="font-body text-text-secondary mt-1">{track.artist}</div>
      <div className="flex flex-wrap gap-2 mt-3">
        {track.bpm && <Tag>{track.bpm} BPM</Tag>}
        {track.camelot && <Tag>{formatKey(track.camelot)}</Tag>}
        {track.vocal_class && (
          <Tag color={VOCAL_COLOR[track.vocal_class]}>
            {VOCAL_LABEL[track.vocal_class] ?? track.vocal_class}
          </Tag>
        )}
        {(track.styles ?? []).slice(0, 3).map(s => (
          <Tag key={s}>{s}</Tag>
        ))}
      </div>
    </div>
  )
}

function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-3 py-1 rounded font-mono transition-colors ${
        active
          ? 'bg-purple-primary text-white'
          : 'bg-surface border border-border text-text-secondary hover:text-text-primary'
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

    // Cap at displayLimit when no filter is active so the default view stays concise
    if (keyFilter === 'all' && !bpmFilter) return results.slice(0, displayLimit)

    return results
  }, [data, keyFilter, bpmFilter, displayLimit])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-80px)] bg-background">
        <div className="w-8 h-8 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
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
        className="text-text-secondary hover:text-text-primary font-body text-sm mb-8 flex items-center gap-1.5 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
        <span className="text-xs font-mono text-text-secondary uppercase tracking-widest mr-1">
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
              onClick={() => navigate(`/results?id=${track.id}`)}
            />
          ))
        )}
      </div>

      {/* Show more — only when unfiltered and there are more results to show */}
      {keyFilter === 'all' && !bpmFilter && data && displayLimit < data.results.length && (
        <button
          onClick={() => setDisplayLimit(n => n + 15)}
          className="w-full mt-4 py-3 border border-border rounded-lg text-text-secondary
                     hover:border-purple-primary hover:text-text-primary font-body text-sm transition-colors"
        >
          Show more ({data.results.length - displayLimit} remaining)
        </button>
      )}
    </div>
  )
}
