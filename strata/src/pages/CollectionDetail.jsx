import { useParams, useNavigate } from 'react-router-dom'
import { PLAYLISTS } from '../data/playlists'
import KeyStrip from '../components/KeyStrip'
import TrackRow from '../components/TrackRow'

export default function CollectionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const playlist = PLAYLISTS.find(p => p.id === id)

  if (!playlist) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-read flex-col items-center justify-center gap-s3 px-s4">
        <p className="text-ink">That collection doesn't exist.</p>
        <button
          onClick={() => navigate('/collections')}
          className="rounded border border-line-control px-s4 py-2 text-sm text-ink
                     transition-colors hover:border-accent hover:text-accent"
        >
          Back to collections
        </button>
      </div>
    )
  }

  // Populated collections aren't wired to the catalogue yet — `trackIds` is
  // empty for every playlist, so this list renders only once they're seeded.
  const tracks = playlist.tracks ?? []
  const count = playlist.trackIds.length

  return (
    <div className="mx-auto max-w-dense px-s4 pb-s6 pt-s5 sm:px-s6">
      <button
        onClick={() => navigate('/collections')}
        className="mb-s4 rounded text-xs uppercase tracking-[0.14em] text-ink-quiet transition-colors hover:text-accent"
      >
        ← Collections
      </button>

      <header className="mb-s5 border-b border-line-strong pb-s4">
        <p className="text-[10px] uppercase tracking-[0.24em] text-ink-quiet">Collection</p>
        <h1 className="mt-s2 font-display text-[clamp(36px,6vw,56px)] font-light leading-none text-ink">
          {playlist.name}
        </h1>
        <p className="mt-s3 max-w-read text-base text-ink-quiet">{playlist.description}</p>
        <div className="mt-s4 flex flex-wrap items-center gap-s4">
          <KeyStrip camelots={tracks.map(t => t.camelot)} />
          <span className="text-xs tabular-nums text-ink-muted">
            {count === 0 ? 'No tracks yet' : `${count} track${count !== 1 ? 's' : ''}`}
          </span>
        </div>
      </header>

      {count === 0 ? (
        <div className="rounded border border-dashed border-line-strong px-s4 py-s6 text-center">
          <p className="text-sm font-medium text-ink">Nothing in here yet</p>
          <p className="mx-auto mt-1 max-w-[280px] text-xs leading-relaxed text-ink-quiet">
            Tracks added to this collection will show up here with their key and tempo.
          </p>
          <button
            onClick={() => navigate('/explore')}
            className="mt-s3 rounded border border-line-control px-s4 py-2 text-sm text-ink
                       transition-colors hover:border-accent hover:text-accent"
          >
            Browse the catalogue
          </button>
        </div>
      ) : (
        <div className="flex flex-col">
          {tracks.map(track => (
            <TrackRow
              key={track.id}
              track={track}
              onClick={() => navigate(`/results?id=${track.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
