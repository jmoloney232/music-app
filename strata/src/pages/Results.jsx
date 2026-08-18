import { useEffect, useState, useMemo, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { compatibleKeys, keyRelationship, shortKeyName } from '../utils/camelot'
import SpotifyButton from '../components/SpotifyButton'

const API = '/api'

const pct = score => Math.round(score * 100)

/**
 * Group the ranked list into closeness tiers. Bands are derived from the
 * returned scores rather than hard-coded: the first two tier boundaries fall
 * on the largest score drop within a 3–5 row window, and everything after the
 * second boundary is "Further out". With scores this compressed (§ the
 * diagnosis doc), tiers are the honest reading — the digits are near-ties.
 */
const TIER_NAMES = ['Nearly the same record', 'Close relatives', 'Further out']

function groupIntoTiers(rows) {
  if (rows.length === 0) return []
  if (rows.length <= 3) return [{ name: TIER_NAMES[0], rows }]

  const drops = i => pct(rows[i - 1].score) - pct(rows[i].score)
  const boundary = (from) => {
    let best = null
    for (let i = from + 3; i <= Math.min(from + 5, rows.length); i++) {
      if (i >= rows.length) break
      if (best === null || drops(i) > drops(best)) best = i
    }
    return best
  }

  const b1 = boundary(0)
  if (b1 === null) return [{ name: TIER_NAMES[0], rows }]
  const b2 = boundary(b1)

  const tiers = [
    { name: TIER_NAMES[0], rows: rows.slice(0, b1) },
    { name: TIER_NAMES[1], rows: b2 === null ? rows.slice(b1) : rows.slice(b1, b2) },
  ]
  if (b2 !== null) tiers.push({ name: TIER_NAMES[2], rows: rows.slice(b2) })
  return tiers.filter(t => t.rows.length > 0)
}

function tierRange(rows) {
  const hi = pct(rows[0].score)
  const lo = pct(rows[rows.length - 1].score)
  return hi === lo ? `${hi}` : `${hi}–${lo}`
}

/* One 1px axis instead of four stat readouts: lowest, median and best as ticks. */
function SpreadAxis({ compared, lowest, median, highest }) {
  const span = highest - lowest || 1
  const medianPos = ((median - lowest) / span) * 100

  return (
    <div className="flex flex-col gap-s3">
      <span className="text-[10px] uppercase tracking-[0.2em] text-ink-quiet">
        {compared.toLocaleString()} compared
      </span>
      <div className="relative h-[22px]" aria-hidden="true">
        <div className="absolute inset-x-0 top-[11px] h-px bg-line-strong" />
        <span className="absolute left-0 top-[4px] h-[15px] w-px bg-ink-muted" />
        <span className="absolute top-[2px] h-[19px] w-px bg-ink-soft" style={{ left: `${medianPos}%` }} />
        <span className="absolute right-0 top-0 h-[23px] w-px bg-accent" />
      </div>
      <div className="flex justify-between text-[11px] uppercase tracking-[0.1em] tabular-nums text-ink-quiet">
        <span>{pct(lowest)} low</span>
        <span>{pct(median)} median</span>
        <span className="text-accent">{pct(highest)} best</span>
      </div>
      <p className="text-xs italic text-ink-quiet">
        A narrow spread — read the order, not the digits.
      </p>
    </div>
  )
}

function RadioOption({ selected, onSelect, children }) {
  return (
    <button
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className="flex items-center gap-[10px] rounded text-sm transition-colors"
    >
      <span
        aria-hidden="true"
        className={`h-[13px] w-[13px] flex-shrink-0 rounded-full ${
          selected ? 'border-4 border-accent' : 'border border-[rgba(243,242,242,0.3)]'
        }`}
      />
      <span className={selected ? 'text-accent' : 'text-ink-soft'}>{children}</span>
    </button>
  )
}

/* A tiered result row: score numeral, title block, key-relationship chip. */
function ResultRow({ track, query, compatible, onClick }) {
  const isCompatible = compatible != null && track.camelot != null && compatible.has(track.camelot)
  const relationship = isCompatible ? keyRelationship(query.camelot, track.camelot) : null
  const keyLabel = relationship
    ? `${track.camelot} · ${relationship}`
    : track.camelot
      ? `${track.camelot} · ${shortKeyName(track.camelot)}`
      : 'key unknown'

  const inBpmRange =
    query.bpm && track.bpm != null &&
    track.bpm >= query.bpm * 0.94 && track.bpm <= query.bpm * 1.06

  const style = (track.styles ?? [])[0]
  const styleLabel = style ? style.split('---').pop().trim() : null

  return (
    <div
      className="group relative grid cursor-pointer grid-cols-[48px_minmax(0,1fr)] items-center gap-x-s3 gap-y-s2
                 border-b border-hairline py-s4 sm:grid-cols-[96px_minmax(0,1fr)_150px] sm:gap-x-[28px] sm:py-[22px]"
    >
      <span
        className={`font-display text-[32px] leading-none tabular-nums sm:text-[54px] ${
          isCompatible ? 'text-accent' : 'text-ink-dim'
        }`}
      >
        {pct(track.score)}
      </span>

      <div className="flex min-w-0 flex-col gap-[5px]">
        <div className="flex min-w-0 items-baseline gap-s3">
          <button
            onClick={onClick}
            className="min-w-0 truncate rounded text-left font-display text-[22px] leading-tight text-ink
                       after:absolute after:inset-0 after:content-[''] sm:text-[32px]"
          >
            {track.title}
          </button>
          <span className="hidden truncate text-[15px] italic text-ink-soft sm:inline">{track.artist}</span>
        </div>
        <span className="truncate text-sm italic text-ink-soft sm:hidden">{track.artist}</span>
        <div className="flex flex-wrap items-center gap-x-[14px] gap-y-1 text-sm tabular-nums text-ink-quiet">
          {track.bpm != null && (
            <span className={inBpmRange || !query.bpm ? '' : 'text-ink-muted'}>{track.bpm.toFixed(1)}</span>
          )}
          {track.vocal_class && (
            <span className="border-l border-line-strong pl-[14px] first:border-l-0 first:pl-0">
              {{ instrumental: 'Instrumental', vocal: 'Vocal', ambiguous: 'Mixed' }[track.vocal_class]}
            </span>
          )}
          {styleLabel && (
            <span className="border-l border-line-strong pl-[14px] first:border-l-0 first:pl-0">{styleLabel}</span>
          )}
          <SpotifyButton artist={track.artist} title={track.title} variant="text" />
        </div>
      </div>

      <div className="col-span-2 flex items-center gap-s3 sm:col-span-1 sm:flex-col sm:items-end sm:gap-[3px]">
        <span
          className={`whitespace-nowrap rounded border px-3 py-[5px] text-sm tabular-nums ${
            isCompatible
              ? 'border-accent text-accent'
              : 'border-line-strong text-ink-soft'
          }`}
        >
          {keyLabel}
        </span>
        {query.bpm && track.bpm != null && (
          <span className="text-[11px] tabular-nums text-ink-muted">
            {Math.round(track.bpm)} · {inBpmRange ? 'within' : 'outside'} ±6%
          </span>
        )}
      </div>
    </div>
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

  const tiers = useMemo(() => groupIntoTiers(filteredResults), [filteredResults])

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
          className="rounded border border-line-control px-s4 py-2 text-sm text-ink
                     transition-colors hover:border-accent hover:text-accent"
        >
          Back to search
        </button>
      </div>
    )
  }

  const filtersActive = keyFilter !== 'all' || bpmFilter
  const q = data.query
  const bpmLo = q.bpm ? Math.round(q.bpm * 0.94) : null
  const bpmHi = q.bpm ? Math.round(q.bpm * 1.06) : null

  return (
    <div className="mx-auto max-w-dense px-s4 pb-s6 pt-s5 sm:px-s6">

      {/* Band 1 — query + spread */}
      <div className="grid grid-cols-1 items-end gap-s5 border-b border-divider pb-s5 lg:grid-cols-[1fr_300px] lg:gap-[56px]">
        <div className="flex min-w-0 flex-col gap-s3">
          <span className="text-[10px] uppercase tracking-[0.24em] text-ink-quiet">Matching against</span>
          <h1 className="min-w-0 font-display text-[clamp(34px,6vw,60px)] font-light leading-none text-ink">
            {q.title}{' '}
            <span className="text-[clamp(22px,3.4vw,34px)] italic text-ink-soft">{q.artist}</span>
          </h1>
          <div className="flex flex-wrap items-center gap-x-s4 gap-y-2 text-sm tabular-nums text-ink-soft">
            {q.bpm != null && <span>{q.bpm.toFixed(1)} BPM</span>}
            {q.camelot && (
              <span className="border-l border-line-strong pl-s4 text-accent first:border-l-0 first:pl-0">
                {q.camelot} / {shortKeyName(q.camelot)?.replace(' min', ' minor').replace(' maj', ' major')}
              </span>
            )}
            {q.vocal_class && (
              <span className="border-l border-line-strong pl-s4">
                {{ instrumental: 'Instrumental', vocal: 'Vocal', ambiguous: 'Mixed' }[q.vocal_class]}
              </span>
            )}
            {(q.styles ?? []).slice(0, 1).map(s => (
              <span key={s} className="rounded-chip border border-line-strong px-[10px] py-[3px] text-[11px] tracking-[0.06em]">
                {s.split('---').pop().trim()}
              </span>
            ))}
            <SpotifyButton artist={q.artist} title={q.title} variant="text" />
          </div>
        </div>
        <SpreadAxis
          compared={data.total_compared}
          lowest={data.lowest}
          median={data.median}
          highest={data.highest}
        />
      </div>

      {/* Band 2 — filters */}
      <div className="flex flex-wrap items-center gap-x-[26px] gap-y-s3 border-b border-divider py-[18px]"
           role="radiogroup" aria-label="Key filter">
        <RadioOption selected={keyFilter === 'all'} onSelect={() => setKeyFilter('all')}>
          Any key
        </RadioOption>
        <RadioOption selected={keyFilter === 'compatible'} onSelect={() => setKeyFilter('compatible')}>
          Keys I can mix into
        </RadioOption>
        <RadioOption selected={keyFilter === 'exact'} onSelect={() => setKeyFilter('exact')}>
          Exactly {q.camelot ?? 'this key'}
        </RadioOption>
        {q.bpm && (
          <>
            <span aria-hidden="true" className="hidden h-4 w-px bg-line-strong sm:inline-block" />
            <label className="flex cursor-pointer select-none items-center gap-[10px] text-sm text-ink-soft">
              <input
                type="checkbox"
                checked={bpmFilter}
                onChange={e => setBpmFilter(e.target.checked)}
                className="h-[13px] w-[13px] rounded-chip border border-accent"
              />
              <span className="tabular-nums">Tempo ±6% · {bpmLo}–{bpmHi}</span>
            </label>
          </>
        )}
        {filtersActive && (
          <span className="ml-auto text-sm tabular-nums text-ink-quiet">
            {filteredResults.length} of {data.results.length}
          </span>
        )}
      </div>

      {/* Band 3 — tiered results */}
      <div className="flex flex-col gap-[30px] pt-[36px]">
        {filteredResults.length === 0 ? (
          <div className="rounded border border-dashed border-line-strong px-s4 py-s5 text-center">
            <p className="text-ink">No matches left after filtering.</p>
            <p className="mt-1 text-sm text-ink-quiet">
              None of the {data.results.length} results are in a compatible key or tempo range.
            </p>
            <button
              onClick={() => { setKeyFilter('all'); setBpmFilter(false) }}
              className="mt-s3 rounded border border-line-control px-s4 py-2 text-sm text-ink
                         transition-colors hover:border-accent hover:text-accent"
            >
              Clear filters
            </button>
          </div>
        ) : (
          tiers.map(tier => (
            <section key={tier.name}>
              <div className="flex items-baseline gap-[18px]">
                <h2 className="font-display text-[26px] font-normal italic text-accent">{tier.name}</h2>
                <span aria-hidden="true" className="h-px flex-1 bg-divider" />
                <span className="text-[11px] uppercase tracking-[0.16em] tabular-nums text-ink-quiet">
                  {tierRange(tier.rows)}
                </span>
              </div>
              <div className="flex flex-col">
                {tier.rows.map(track => (
                  <ResultRow
                    key={track.id}
                    track={track}
                    query={q}
                    compatible={compatibleSet}
                    onClick={() => navigate(`/results?id=${track.id}`)}
                  />
                ))}
              </div>
            </section>
          ))
        )}

        {filteredResults.length > 0 && (
          <div className="flex flex-wrap items-center gap-s4 pt-s2">
            {keyFilter === 'all' && !bpmFilter && displayLimit < data.results.length && (
              <button
                onClick={() => setDisplayLimit(n => n + 15)}
                className="rounded border border-accent px-[26px] py-[10px] text-sm text-accent
                           transition-colors hover:bg-accent-fill"
              >
                Show 15 more
              </button>
            )}
            <span className="text-sm italic text-ink-quiet">
              Gold numerals and gold key chips are the records you can mix into
              {q.camelot ? ` from ${q.camelot}` : ''}. Any row becomes the next query.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
