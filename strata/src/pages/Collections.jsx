import { useNavigate } from 'react-router-dom'
import { PLAYLISTS } from '../data/playlists'
import KeyStrip from '../components/KeyStrip'

function PlaylistCard({ playlist, onClick }) {
  const count = playlist.trackIds.length
  const camelots = playlist.camelots ?? []

  return (
    <button
      onClick={onClick}
      className="group flex w-full flex-col gap-s3 rounded border border-hairline bg-surface p-s4
                 text-left transition-colors hover:border-line-strong hover:bg-sunken"
    >
      <div>
        <div className="text-md font-semibold leading-tight text-ink">{playlist.name}</div>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-quiet">{playlist.description}</p>
      </div>

      <div className="mt-auto flex flex-col gap-s2">
        <KeyStrip camelots={camelots} />
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs tabular-nums text-ink-muted">
            {count === 0 ? 'No tracks yet' : `${count} track${count !== 1 ? 's' : ''}`}
          </span>
          <span className="text-xs text-ink-quiet transition-colors group-hover:text-accent">
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
    <div className="mx-auto max-w-dense px-s4 py-s5">
      <div className="mb-s5">
        <h1 className="text-xl font-semibold text-ink">Collections</h1>
        <p className="mt-1 text-sm text-ink-quiet">
          Groupings you keep by hand, separate from what the embeddings find.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-s3 sm:grid-cols-2 lg:grid-cols-3">
        {PLAYLISTS.map(playlist => (
          <PlaylistCard
            key={playlist.id}
            playlist={playlist}
            onClick={() => navigate(`/collections/${playlist.id}`)}
          />
        ))}
      </div>
    </div>
  )
}
