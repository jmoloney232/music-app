import { Link, useLocation } from 'react-router-dom'

const LINKS = [
  { to: '/explore', label: 'Explore', match: p => p === '/explore' },
  { to: '/collections', label: 'Collections', match: p => p.startsWith('/collections') },
  { to: '/dj', label: 'DJ Mode', match: p => p === '/dj' },
]

export default function Nav() {
  const { pathname } = useLocation()

  return (
    <nav className="fixed inset-x-0 top-0 z-50 border-b border-hairline bg-canvas/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-dense items-center justify-between gap-s4 px-s4 sm:h-20 sm:px-s5">
        {/* Below 640px the full wordmark and three links can't share a line
            without both wrapping, so the wordmark drops to its initials. */}
        <Link
          to="/"
          className="flex-shrink-0 rounded text-sm font-semibold uppercase tracking-[0.18em] text-ink
                     transition-colors hover:text-accent sm:text-base"
        >
          <span className="sm:hidden" aria-hidden="true">SSS</span>
          <span className="hidden sm:inline">Similar Song Search</span>
          <span className="sr-only sm:hidden">Similar Song Search</span>
        </Link>

        <div className="flex items-center gap-s1 sm:gap-s3">
          {LINKS.map(({ to, label, match }) => {
            const active = match(pathname)
            return (
              <Link
                key={to}
                to={to}
                aria-current={active ? 'page' : undefined}
                className={`whitespace-nowrap rounded px-2 py-1.5 text-sm transition-colors sm:px-3 ${
                  active
                    ? 'bg-tan font-medium text-ink'
                    : 'text-ink-quiet hover:bg-sunken hover:text-ink'
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
