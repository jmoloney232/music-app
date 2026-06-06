import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const API = '/api'

// Update with real artists/titles from your catalog
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
      setLoading(true)
      setFetchError(null)
      try {
        const res = await fetch(`${API}/search?q=${encodeURIComponent(query.trim())}`)
        if (res.ok) setResults(await res.json())
        else { setResults([]); setFetchError(`API error: ${res.status}`) }
      } catch (e) {
        setResults([])
        setFetchError(e.message)
      } finally {
        setLoading(false)
        setSearched(true)
      }
    }, 300)
    return () => clearTimeout(debounce.current)
  }, [query])

  return (
    <div className="relative min-h-[calc(100vh-80px)] bg-background flex flex-col items-center px-6 pt-24 pb-16 overflow-hidden">

      {/* Background glow */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute left-1/2 top-[-140px] -translate-x-1/2 w-[1000px] h-[750px] rounded-full opacity-55"
          style={{ background: 'radial-gradient(ellipse at center, rgba(123,47,190,0.45) 0%, rgba(123,47,190,0.15) 45%, transparent 70%)' }}
        />
      </div>

      {/* Hero */}
      <div className="relative text-center mb-10 max-w-3xl animate-fade-up">
        <h1 className="font-headline font-bold text-7xl text-text-primary tracking-tight mb-5 leading-[1.05]">
          Find Your{' '}
          <span className="bg-gradient-to-r from-purple-light to-purple-primary bg-clip-text text-transparent">
            Next Record
          </span>
        </h1>
        <p className="font-body text-text-secondary text-xl">
          Search any track in the catalog and find sonically similar songs.
        </p>
      </div>

      {/* Search bar */}
      <div className="relative w-full max-w-2xl mb-8 animate-fade-up" style={{ animationDelay: '80ms' }}>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search artist or title…"
          className="w-full bg-surface border border-border rounded-2xl px-6 py-5
                     font-body text-text-primary placeholder-text-secondary text-lg
                     focus:outline-none focus:border-purple-primary
                     transition-all duration-200
                     focus:shadow-[0_0_0_3px_rgba(123,47,190,0.25)]"
          autoFocus
        />
        {loading && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2">
            <div className="w-5 h-5 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Example searches — shown before the user types */}
      {!query && (
        <div className="w-full max-w-2xl animate-fade-in" style={{ animationDelay: '160ms' }}>
          <p className="text-sm font-body text-text-secondary mb-4 text-center">Try searching for</p>
          <div className="flex flex-wrap gap-2 justify-center">
            {EXAMPLE_SEARCHES.map(q => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="text-sm font-body text-text-secondary border border-border rounded-full px-4 py-2
                           hover:border-purple-primary hover:text-text-primary transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Cold-start notice */}
      {slowLoad && (
        <p className="text-text-secondary font-body text-sm mb-4 animate-pulse">
          Waking up the server — first load can take up to 30s…
        </p>
      )}

      {/* Error / empty state */}
      {fetchError && (
        <p className="text-red-400 font-mono text-xs mb-2">Error: {fetchError}</p>
      )}
      {searched && results.length === 0 && !loading && !fetchError && (
        <p className="text-text-secondary font-body text-sm">No tracks found for "{query}"</p>
      )}

      {/* Results list */}
      {results.length > 0 && (
        <ul className="w-full max-w-2xl divide-y divide-border rounded-xl border border-border overflow-hidden animate-fade-in">
          {results.map((track, i) => (
            <li
              key={track.id}
              className="animate-fade-up"
              style={{ animationDelay: `${Math.min(i * 30, 240)}ms` }}
            >
              <button
                onClick={() => navigate(`/results?id=${track.id}`)}
                className="w-full flex items-center justify-between px-5 py-4 bg-surface
                           hover:bg-[#1a1a1a] transition-all duration-150 text-left group"
              >
                <div>
                  <span className="font-body font-medium text-text-primary group-hover:text-white transition-colors">
                    {track.artist}
                  </span>
                  <span className="text-text-secondary mx-2">—</span>
                  <span className="font-body text-text-secondary group-hover:text-text-primary transition-colors">
                    {track.title}
                  </span>
                </div>
                <svg
                  className="w-4 h-4 text-text-secondary group-hover:text-purple-light transition-all duration-150 group-hover:translate-x-0.5 flex-shrink-0 ml-4"
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
