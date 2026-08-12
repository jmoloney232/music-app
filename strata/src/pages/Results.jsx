import { useEffect, useState, useMemo, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { compatibleKeys, keyColor } from '../utils/camelot'
import SpotifyButton from '../components/SpotifyButton'
import TrackRow, { TrackMeta } from '../components/TrackRow'

const API = '/api'

function QueryCard({ track }) {
  return (
    <section
      className="mb-s4 rounded-panel bg-tan px-s4 py-s4"
      style={
        track.camelot
          ? { borderLeft: `4px solid ${keyColor(track.camelot, 'selected')}` }
          : { borderLeft: '4px solid #8E7F6E' }
      }
    >
      <div className="flex items-start justify-between gap-s3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.16em] text-ink-quiet">Matching against</p>
          <h1 className="mt-1.5 text-lg font-semibold leading-tight text-ink">{track.title}</h1>
          <p className="text-ink-quiet">{track.artist}</p>
        </div>
        <SpotifyButton artist={track.artist} title={track.title} />
      </div>
      <div className="mt-s3">
        <TrackMeta track={track} styleLimit={3} />
      </div>
    </section>
  )
}

function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`h-control-sm rounded border px-s3 text-sm transition-colors ${
        active
          ? 'border-accent bg-accent font-medium text-white'
          : 'border-hairline text-ink-quiet hover:border-line-strong hover:bg-sunken hover:text-ink'
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
  const latestRequest = useRef(0)

  useEffect(() => {
    if (!trackId) {
      setError('No track selected.')
      setLoading(false)
      return
    }
    const requestId = ++latestRequest.current
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
      .then(d => { if (requestId === latestRequest.current) setData(d) })
      .catch(e => { if (requestId === latestRequest.current) setError(e.message) })
      .finally(() => { if (requestId === latestRequest.current) setLoading(false) })
  }, [trackId])

  // The same set the filter uses also marks the rows, so a DJ can see which
  // tracks mix without having to switch the filter on.
  const compatibleSet = useMemo(
    () => (data?.query.camelot ? new Set(compatibleKeys(data.query.camelot)) : null),
    [data],
  )

  const filteredResults = useMemo(() => {
    if (!data) return []
    let results = data.results

    if (keyFilter === 'compatible') {
      const compat = compatibleSet ?? new Set()
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
  }, [data, keyFilter, bpmFilter, displayLimit, compatibleSet])

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-read flex-col items-center justify-center gap-s3 px-s4">
        <div
          role="status"
          className="h-6 w-6 animate-spin rounded-full border-2 border-line-strong border-t-accent"
        />
        <p className="text-sm text-ink-quiet">Comparing against the catalogue…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-read flex-col items-center justify-center gap-s3 px-s4 text-center">
        <p className="text-ink">Couldn't load similar tracks.</p>
        <p className="text-sm text-ink-quiet">{error}</p>
        <button
          onClick={() => navigate('/')}
          className="h-control rounded border border-line-control px-s3 text-sm text-ink
                     transition-colors hover:bg-sunken"
        >
          Back to search
        </button>
      </div>
    )
  }

  const filtersActive = keyFilter !== 'all' || bpmFilter

  return (
    <div className="mx-auto max-w-read px-s4 py-s5">
      <button
        onClick={() => navigate('/')}
        className="mb-s4 rounded text-sm text-ink-quiet transition-colors hover:text-accent"
      >
        ← Back to search
      </button>

      <QueryCard track={data.query} />

      <dl className="mb-s4 flex flex-wrap gap-x-s4 gap-y-1 text-sm">
        <div className="flex gap-1.5">
          <dt className="text-ink-quiet">Compared</dt>
          <dd className="font-mono tabular-nums text-ink">{data.total_compared.toLocaleString()}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-ink-quiet">Best</dt>
          <dd className="font-mono tabular-nums text-ink">{Math.round(data.highest * 100)}%</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-ink-quiet">Median</dt>
          <dd className="font-mono tabular-nums text-ink">{Math.round(data.median * 100)}%</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-ink-quiet">Lowest</dt>
          <dd className="font-mono tabular-nums text-ink">{Math.round(data.lowest * 100)}%</dd>
        </div>
      </dl>

      <div className="mb-s4 flex flex-wrap items-center gap-s2 border-y border-hairline py-s3">
        <span className="text-xs uppercase tracking-[0.16em] text-ink-quiet">Filter</span>
        <FilterPill active={keyFilter === 'all'} onClick={() => setKeyFilter('all')}>
          All
        </FilterPill>
        <FilterPill active={keyFilter === 'compatible'} onClick={() => setKeyFilter('compatible')}>
          Compatible keys
        </FilterPill>
        <FilterPill active={keyFilter === 'exact'} onClick={() => setKeyFilter('exact')}>
          Exact key
        </FilterPill>
        {data.query.bpm && (
          <FilterPill active={bpmFilter} onClick={() => setBpmFilter(v => !v)}>
            BPM ±6%
          </FilterPill>
        )}
        {filtersActive && (
          <span className="ml-auto font-mono text-xs tabular-nums text-ink-quiet">
            {filteredResults.length} of {data.results.length}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-s2">
        {filteredResults.length === 0 ? (
          <div className="rounded border border-dashed border-line-strong px-s4 py-s5 text-center">
            <p className="text-ink">No matches left after filtering.</p>
            <p className="mt-1 text-sm text-ink-quiet">
              None of the {data.results.length} results are in a compatible key or tempo range.
            </p>
            <button
              onClick={() => { setKeyFilter('all'); setBpmFilter(false) }}
              className="mt-s3 h-control rounded border border-line-control px-s3 text-sm text-ink
                         transition-colors hover:bg-sunken"
            >
              Clear filters
            </button>
          </div>
        ) : (
          filteredResults.map((track, i) => (
            <TrackRow
              key={track.id}
              track={track}
              rank={i + 1}
              score={track.score}
              compatible={compatibleSet}
              onClick={() => navigate(`/results?id=${track.id}`)}
            />
          ))
        )}
      </div>

      {keyFilter === 'all' && !bpmFilter && data && displayLimit < data.results.length && (
        <button
          onClick={() => setDisplayLimit(n => n + 15)}
          className="mt-s3 h-control w-full rounded border border-line-control text-sm text-ink-quiet
                     transition-colors hover:bg-sunken hover:text-ink"
        >
          Show 15 more ({data.results.length - displayLimit} remaining)
        </button>
      )}
    </div>
  )
}
