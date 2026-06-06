import { Link, useLocation } from 'react-router-dom'

export default function Nav() {
  const { pathname } = useLocation()

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-20 flex items-center justify-between px-8
                    bg-surface/80 backdrop-blur-md border-b border-border">
      <Link to="/" className="font-headline font-bold text-xl tracking-widest hover:opacity-80 transition-opacity">
        <span className="bg-gradient-to-r from-purple-light to-purple-primary bg-clip-text text-transparent">
          JACK'S SIMILAR SONG SEARCH
        </span>
      </Link>

      <div className="flex items-center gap-6">
        <Link
          to="/explore"
          className={`text-sm font-body transition-colors ${
            pathname === '/explore'
              ? 'text-purple-light'
              : 'text-text-secondary hover:text-text-primary'
          }`}
        >
          Explore
        </Link>
        <a href="#" className="text-text-secondary hover:text-text-primary text-sm font-body transition-colors">
          Collections
        </a>
        <Link
          to="/dj"
          className={`px-4 py-2 rounded text-sm font-headline font-semibold transition-all duration-200 ${
            pathname === '/dj'
              ? 'bg-purple-light text-white shadow-[0_0_20px_rgba(168,85,247,0.4)]'
              : 'bg-purple-primary hover:bg-purple-light text-white hover:shadow-[0_0_16px_rgba(168,85,247,0.3)]'
          }`}
        >
          DJ MODE
        </Link>
      </div>
    </nav>
  )
}
