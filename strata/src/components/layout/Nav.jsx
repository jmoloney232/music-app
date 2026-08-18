import { Link, useLocation } from 'react-router-dom'

// Booth shows all four destinations; the wordmark still links home. Results is
// reached from Search, so it keeps that link lit.
const LINKS = [
  { to: '/', label: 'Search', match: p => p === '/' || p === '/results' },
  { to: '/explore', label: 'Explore', match: p => p === '/explore' },
  { to: '/dj', label: 'DJ Mode', match: p => p === '/dj' },
  { to: '/collections', label: 'Collections', match: p => p.startsWith('/collections') },
]

export default function Nav() {
  const { pathname } = useLocation()

  return (
    <nav className="fixed inset-x-0 top-0 z-50 border-b border-divider bg-canvas/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-dense items-center justify-between gap-s4 px-s4 sm:h-20 sm:px-s6">
        {/* Below 640px the full wordmark and four links can't share a line
            without both wrapping, so the wordmark drops to its initials. */}
        <Link
          to="/"
          className="flex-shrink-0 rounded font-display text-[22px] font-normal uppercase tracking-[0.24em] text-ink
                     transition-colors hover:text-accent"
        >
          <span className="sm:hidden" aria-hidden="true">SSS</span>
          <span className="hidden sm:inline">Similar Song Search</span>
          <span className="sr-only sm:hidden">Similar Song Search</span>
        </Link>

        <div className="flex items-center gap-s2 sm:gap-[34px]">
          {LINKS.map(({ to, label, match }) => {
            const active = match(pathname)
            return (
              <Link
                key={to}
                to={to}
                aria-current={active ? 'page' : undefined}
                className={`whitespace-nowrap pb-[3px] text-[11px] uppercase tracking-[0.06em] transition-colors sm:text-xs sm:tracking-[0.14em] ${
                  active
                    ? 'border-b border-accent text-accent'
                    : 'text-ink-quiet hover:text-ink'
                }`}
              >
                {label}
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
