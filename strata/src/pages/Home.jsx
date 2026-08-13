import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const API = '/api'

const EXAMPLE_SEARCHES = [
  'Aphex Twin', 'Four Tet', 'Burial', 'Daft Punk', 'Boards of Canada', 'Jamie xx',
]

export default function Home() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [slowLoad, setSlowLoad] = useState(false)
  const [searched, setSearched] = useState(false)
  const [fetchError, setFetchError] = useState(null)
  const navigate = useNavigate()
  const debounce = useRef(null)
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

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      setSearched(false)
      return
    }
    clearTimeout(debounce.current)
    debounce.current = setTimeout(async () => {
      // Responses can land out of order; only the newest query may write state.
      const requestId = ++latestRequest.current
      setLoading(true)
      setFetchError(null)
      try {
        const res = await fetch(`${API}/search?q=${encodeURIComponent(query.trim())}`)
        if (requestId !== latestRequest.current) return
        if (res.ok) setResults(await res.json())
        else { setResults([]); setFetchError(`Search failed (HTTP ${res.status})`) }
      } catch (e) {
        if (requestId !== latestRequest.current) return
        setResults([])
        setFetchError(e.message)
      } finally {
        if (requestId === latestRequest.current) {
          setLoading(false)
          setSearched(true)
        }
      }
    }, 300)
    return () => clearTimeout(debounce.current)
  }, [query])

  return (
    <div className="mx-auto flex max-w-read flex-col px-s4 pb-s6 pt-s6 sm:pt-[72px]">

      <header className="mb-s5">
        <h1 className="text-2xl font-semibold leading-[1.08] tracking-[-0.02em] text-ink sm:text-3xl">
          Find tracks that<br />actually sound alike
        </h1>
        <p className="mt-s3 max-w-[52ch] text-ink-quiet">
          Every track in the catalogue is compared by its audio, not its genre tag. Pick one and
          you'll get the closest matches ranked, with BPM and harmonic key for mixing.
        </p>
      </header>

      <div className="relative mb-s4">
        <label htmlFor="track-search" className="sr-only">Search the catalogue by artist or title</label>
        <input
          id="track-search"
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Artist or title…"
          autoComplete="off"
          className="h-control-lg w-full rounded border border-line-control bg-surface px-s3 pr-11
                     text-base text-ink placeholder:text-ink-muted
                     focus:border-accent focus:outline-none focus-visible:outline-none"
          autoFocus
        />
        {loading && (
          <div
            role="status"
            aria-label="Searching"
            className="absolute right-s3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin rounded-full
                       border-2 border-line-strong border-t-accent"
          />
        )}
      </div>

      {!query && (
        <div className="mb-s4">
          <p className="mb-s2 text-sm text-ink-quiet">Artists in the catalogue to start from</p>
          <div className="flex flex-wrap gap-s2">
            {EXAMPLE_SEARCHES.map(q => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="h-control-sm rounded border border-hairline px-s3 text-sm text-ink-quiet
                           transition-colors hover:border-line-strong hover:bg-sunken hover:text-ink"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      <div aria-live="polite" className="min-w-0">
        {slowLoad && (
          <p className="mb-s3 text-sm text-ink-muted">
            Waking up the server — the first search after a while can take up to 30s.
          </p>
        )}

        {fetchError && (
          <p className="mb-s3 rounded border border-error/40 bg-error/5 px-s3 py-2 text-sm text-error">
            {fetchError}. Check your connection and try again.
          </p>
        )}

        {searched && results.length === 0 && !loading && !fetchError && (
          <p className="text-sm text-ink-quiet">
            Nothing in the catalogue matches “{query}”. Try a different spelling, or browse{' '}
            <button onClick={() => navigate('/explore')} className="rounded text-accent underline underline-offset-2 hover:text-accent-deep">
              the full catalogue
            </button>.
          </p>
        )}

        {results.length > 0 && (
          <ul className="divide-y divide-hairline overflow-hidden rounded border border-hairline bg-surface">
            {results.map(track => (
              <li key={track.id}>
                <button
                  onClick={() => navigate(`/results?id=${track.id}`)}
                  className="flex w-full items-baseline gap-s2 px-s3 py-2.5 text-left
                             transition-colors hover:bg-sunken"
                >
                  <span className="truncate font-medium text-ink">{track.artist}</span>
                  <span className="truncate text-sm text-ink-quiet">{track.title}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
