import { Link } from 'react-router-dom'

export default function Nav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-20 flex items-center justify-between px-8
                    bg-surface/80 backdrop-blur-md border-b border-border">
      <Link to="/" className="font-headline font-bold text-xl tracking-widest text-text-primary hover:text-white transition-colors">
        JACK'S SIMILAR SONG SEARCH
      </Link>
      <div className="flex items-center gap-6">
        <a href="#" className="text-text-secondary hover:text-text-primary text-sm font-body transition-colors">
          Explore
        </a>
        <a href="#" className="text-text-secondary hover:text-text-primary text-sm font-body transition-colors">
          Collections
        </a>
        <Link
          to="/dj"
          className="bg-purple-primary hover:bg-purple-light text-white px-4 py-2 rounded
                     text-sm font-headline font-semibold transition-colors"
        >
          DJ MODE
        </Link>
      </div>
    </nav>
  )
}
