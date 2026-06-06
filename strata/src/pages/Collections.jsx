import { useNavigate } from 'react-router-dom'
import { PLAYLISTS } from '../data/playlists'

function PlaylistCard({ playlist, onClick, index = 0 }) {
  const { from, via, to } = playlist.colors
  const count = playlist.trackIds.length

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-surface rounded-2xl overflow-hidden border border-border
                 hover:border-purple-primary/40
                 hover:shadow-[0_8px_40px_rgba(0,0,0,0.6),0_0_0_1px_rgba(123,47,190,0.15)]
                 transition-all duration-200 group animate-fade-up"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Gradient artwork */}
      <div
        className="relative h-44 overflow-hidden"
        style={{ background: `linear-gradient(135deg, ${from} 0%, ${via} 55%, ${to} 100%)` }}
      >
        {/* Decorative music note */}
        <svg
          className="absolute -bottom-3 -right-3 w-32 h-32 opacity-10 group-hover:opacity-[0.18] transition-opacity duration-300"
          fill="none" viewBox="0 0 24 24" stroke="white" strokeWidth={0.6}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
        </svg>
        {/* Fade artwork into card body */}
        <div className="absolute bottom-0 inset-x-0 h-16 bg-gradient-to-t from-surface to-transparent" />
      </div>

      {/* Info */}
      <div className="px-5 pb-5 -mt-2">
        <div className="font-headline font-bold text-lg text-text-primary group-hover:text-white transition-colors leading-tight mb-1.5">
          {playlist.name}
        </div>
        <p className="font-body text-xs text-text-secondary leading-relaxed line-clamp-2 mb-4">
          {playlist.description}
        </p>
        <div className="flex items-center justify-between">
          <span className="text-xs font-body text-text-subtle">
            {count === 0 ? 'No tracks yet' : `${count} track${count !== 1 ? 's' : ''}`}
          </span>
          <span className="text-xs font-body text-purple-light translate-x-1 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-all duration-200">
            Open →
          </span>
        </div>
      </div>
    </button>
  )
}

export default function Collections() {
  const navigate = useNavigate()

  return (
    <div className="min-h-[calc(100vh-80px)] bg-background px-6 py-10">
      <div className="max-w-6xl mx-auto">
        <div className="mb-10 animate-fade-up">
          <h1 className="font-headline font-bold text-4xl text-text-primary tracking-tight mb-2">
            Collections
          </h1>
          <p className="font-body text-text-secondary">
            Curated playlists from the catalog — click in to explore.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-5">
          {PLAYLISTS.map((playlist, i) => (
            <PlaylistCard
              key={playlist.id}
              playlist={playlist}
              index={i}
              onClick={() => navigate(`/collections/${playlist.id}`)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
