import { useParams, useNavigate } from 'react-router-dom'
import { PLAYLISTS } from '../data/playlists'

export default function CollectionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const playlist = PLAYLISTS.find(p => p.id === id)

  if (!playlist) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-80px)] bg-background gap-4">
        <p className="text-text-secondary font-body">Playlist not found.</p>
        <button
          onClick={() => navigate('/collections')}
          className="text-purple-light font-body text-sm hover:text-white transition-colors"
        >
          ← Back to Collections
        </button>
      </div>
    )
  }

  const { from, via, to } = playlist.colors
  const count = playlist.trackIds.length

  return (
    <div className="min-h-[calc(100vh-80px)] bg-background">

      {/* Gradient header — fades to page background */}
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0"
          style={{ background: `linear-gradient(135deg, ${from} 0%, ${via} 55%, ${to} 100%)` }}
        />
        <div className="absolute bottom-0 inset-x-0 h-2/3 bg-gradient-to-t from-background to-transparent" />

        <div className="relative max-w-6xl mx-auto px-6 pt-12 pb-16">
          <button
            onClick={() => navigate('/collections')}
            className="text-text-secondary hover:text-text-primary font-body text-sm mb-10
                       flex items-center gap-1.5 transition-colors group"
          >
            <svg
              className="w-4 h-4 transition-transform duration-150 group-hover:-translate-x-0.5"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Collections
          </button>

          <p className="text-xs font-body text-text-secondary uppercase tracking-widest mb-3">
            Playlist
          </p>
          <h1 className="font-headline font-bold text-5xl text-text-primary leading-tight mb-3">
            {playlist.name}
          </h1>
          <p className="font-body text-text-secondary text-lg max-w-2xl mb-5">
            {playlist.description}
          </p>
          <span className="text-xs font-body text-text-subtle">
            {count === 0 ? 'No tracks yet' : `${count} track${count !== 1 ? 's' : ''}`}
          </span>
        </div>
      </div>

      {/* Track list */}
      <div className="max-w-6xl mx-auto px-6 pb-16">
        {count === 0 ? (
          <div className="border border-dashed border-border rounded-2xl py-24 flex flex-col items-center gap-4">
            <div className="w-14 h-14 rounded-full border border-border flex items-center justify-center">
              <svg
                className="w-6 h-6 text-text-subtle"
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-text-primary font-body text-sm font-medium mb-1">No tracks yet</p>
              <p className="text-text-secondary font-body text-xs leading-relaxed max-w-[260px]">
                This playlist is empty. Tracks will appear here once added.
              </p>
            </div>
            <button
              onClick={() => navigate('/explore')}
              className="mt-2 px-4 py-2 text-xs font-body border border-border rounded-lg
                         text-text-secondary hover:border-purple-primary hover:text-text-primary transition-colors"
            >
              Browse catalog →
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {/* TrackRow items rendered here once tracks are wired */}
          </div>
        )}
      </div>
    </div>
  )
}
