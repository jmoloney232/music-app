import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const API = '/api'

export default function Home() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [fetchError, setFetchError] = useState(null)
  const navigate = useNavigate()
  const debounce = useRef(null)

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
    <div className="min-h-[calc(100vh-80px)] bg-background flex flex-col items-center px-6 pt-24 pb-16">
      {/* Hero */}
      <div className="text-center mb-12 max-w-2xl">
        <h1 className="font-headline font-bold text-5xl text-text-primary tracking-tight mb-4">
          Find Your Next Record
        </h1>
        <p className="font-body text-text-secondary text-lg">
          Search any track in the catalog. Pick one. See what sounds like it.
        </p>
      </div>

      {/* Search bar */}
      <div className="w-full max-w-2xl mb-8">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search artist or title…"
            className="w-full bg-surface border border-border rounded-lg px-5 py-4
                       font-body text-text-primary placeholder-text-secondary text-base
                       focus:outline-none focus:border-purple-primary transition-colors"
            autoFocus
          />
          {loading && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <div className="w-5 h-5 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
      </div>

      {/* Results list */}
      {fetchError && (
        <p className="text-red-400 font-mono text-xs mb-2">Error: {fetchError}</p>
      )}
      {searched && results.length === 0 && !loading && !fetchError && (
        <p className="text-text-secondary font-body text-sm">No tracks found for "{query}"</p>
      )}

      {results.length > 0 && (
        <ul className="w-full max-w-2xl divide-y divide-border rounded-lg border border-border overflow-hidden">
          {results.map(track => (
            <li key={track.id}>
              <button
                onClick={() => navigate(`/results?id=${track.id}`)}
                className="w-full flex items-center justify-between px-5 py-4 bg-surface
                           hover:bg-border transition-colors text-left group"
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
                <svg className="w-4 h-4 text-text-secondary group-hover:text-purple-light transition-colors flex-shrink-0 ml-4"
                     fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
