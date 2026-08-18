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
  const [catalogueTotal, setCatalogueTotal] = useState(null)
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

  // The kicker states the real catalogue size, not a hard-coded one.
  useEffect(() => {
    fetch(`${API}/explore/tracks?limit=1`)
      .then(r => r.json())
      .then(d => setCatalogueTotal(d.total))
      .catch(() => {})
  }, [])

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
    <div className="mx-auto flex max-w-[1020px] flex-col items-center px-s4 pb-s6 pt-[64px] text-center sm:pt-[110px]">

      <header className="mb-[56px] flex flex-col items-center gap-s4">
        <p className="text-[11px] uppercase tracking-[0.28em] text-ink-quiet">
          {catalogueTotal != null
            ? `${catalogueTotal.toLocaleString()} tracks · analysed from the audio, not the tags`
            : 'Analysed from the audio, not the tags'}
        </p>
        <h1 className="font-display text-[clamp(48px,9vw,86px)] font-light leading-[0.95] tracking-[-0.02em] text-ink">
          What else sounds<br />
          <span className="italic text-accent">like this?</span>
        </h1>
      </header>

      <div className="w-full max-w-[780px] text-left">
        <div className="relative border-b border-accent pb-[18px]">
          <label htmlFor="track-search" className="sr-only">Search the catalogue by artist or title</label>
          <div className="flex items-center gap-s4 px-1">
            <span aria-hidden="true" className="text-[22px] leading-none text-accent">⌕</span>
            <input
              id="track-search"
              type="search"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Artist or title…"
              autoComplete="off"
              className="w-full border-none bg-transparent font-display text-[clamp(26px,5vw,38px)] font-normal
                         leading-tight text-ink caret-accent outline-none placeholder:text-ink-muted
                         focus:outline-none focus-visible:outline-none
                         [&::-webkit-search-cancel-button]:hidden"
              autoFocus
            />
            {loading && (
              <div
                role="status"
                aria-label="Searching"
                className="h-5 w-5 flex-shrink-0 animate-spin rounded-full border-2 border-line-strong border-t-accent"
              />
            )}
          </div>
        </div>

        <div aria-live="polite" className="min-w-0">
          {fetchError && (
            <p className="mt-s4 rounded border border-error/40 px-s3 py-2 text-sm text-error">
              {fetchError}. Check your connection and try again.
            </p>
          )}

          {searched && results.length === 0 && !loading && !fetchError && (
            <p className="mt-s4 text-sm text-ink-quiet">
              Nothing in the catalogue matches “{query}”. Try a different spelling, or browse{' '}
              <button
                onClick={() => navigate('/explore')}
                className="rounded text-accent underline underline-offset-2 hover:text-accent-deep"
              >
                the full catalogue
              </button>.
            </p>
          )}

          {results.length > 0 && (
            <ul>
              {results.map(track => (
                <li key={track.id} className="border-b border-hairline">
                  <button
                    onClick={() => navigate(`/results?id=${track.id}`)}
                    className="group flex w-full items-baseline justify-between gap-s4 px-1 py-[18px] text-left"
                  >
                    <span className="flex min-w-0 items-baseline gap-s3">
                      <span className="truncate font-display text-[26px] leading-tight text-ink
                                       transition-colors group-hover:text-accent group-focus-visible:text-accent">
                        {track.title}
                      </span>
                      <span className="truncate text-sm text-ink-quiet">{track.artist}</span>
                    </span>
                    <span
                      aria-hidden="true"
                      className="hidden flex-shrink-0 text-[11px] uppercase tracking-[0.16em] text-accent
                                 group-hover:inline group-focus-visible:inline"
                    >
                      ⏎ open
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {!query && (
        <div className="mt-[56px] flex flex-wrap items-center justify-center gap-s3 text-sm italic text-ink-quiet">
          <span>Or start from</span>
          {EXAMPLE_SEARCHES.map(q => (
            <button
              key={q}
              onClick={() => setQuery(q)}
              className="rounded border border-line-strong px-[15px] py-[7px] text-sm not-italic text-ink-soft
                         transition-colors hover:border-accent hover:text-accent"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {slowLoad && (
        <div className="mt-[26px] flex w-full max-w-[780px] items-center justify-center gap-s3 border-t border-divider pt-[26px]">
          <span aria-hidden="true" className="h-[9px] w-[9px] flex-shrink-0 rounded-full border border-accent" />
          <span className="text-sm italic text-ink-soft">
            Waking the server. It sleeps when idle — the first search can take 30 seconds.
          </span>
        </div>
      )}
    </div>
  )
}
