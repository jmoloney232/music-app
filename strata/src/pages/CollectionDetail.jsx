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
          className="h-control rounded border border-line-control px-s3 text-sm text-ink
                     transition-colors hover:bg-sunken"
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
    <div className="mx-auto max-w-dense px-s4 py-s5">
      <button
        onClick={() => navigate('/collections')}
        className="mb-s4 rounded text-sm text-ink-quiet transition-colors hover:text-accent"
      >
        ← Collections
      </button>

      <header className="mb-s5 rounded-panel bg-tan px-s4 py-s4">
        <p className="text-xs uppercase tracking-[0.16em] text-ink-quiet">Collection</p>
        <h1 className="mt-1.5 text-xl font-semibold leading-tight text-ink">{playlist.name}</h1>
        <p className="mt-1.5 max-w-read text-ink-quiet">{playlist.description}</p>
        <div className="mt-s3 flex flex-col gap-s2">
          <KeyStrip camelots={tracks.map(t => t.camelot)} limit={32} />
          <span className="font-mono text-xs tabular-nums text-ink-muted">
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
            className="mt-s3 h-control rounded border border-line-control px-s3 text-sm text-ink
                       transition-colors hover:bg-sunken"
          >
            Browse the catalogue
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-s2">
          {tracks.map((track, i) => (
            <TrackRow
              key={track.id}
              track={track}
              rank={i + 1}
              showStyles
              onClick={() => navigate(`/results?id=${track.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
