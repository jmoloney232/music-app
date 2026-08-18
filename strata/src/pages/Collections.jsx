import { useNavigate } from 'react-router-dom'
import { PLAYLISTS } from '../data/playlists'
import KeyStrip from '../components/KeyStrip'

function PlaylistCard({ playlist, onClick }) {
  const count = playlist.trackIds.length
  const camelots = playlist.camelots ?? []

  return (
    <button
      onClick={onClick}
      className="group flex w-full flex-col gap-s3 rounded border border-[rgba(243,242,242,0.16)] p-[26px]
                 text-left transition-colors hover:border-accent"
      style={{ minHeight: 186 }}
    >
      <h2 className="font-display text-[28px] font-normal leading-tight text-ink">{playlist.name}</h2>
      <p className="text-sm leading-[1.7] text-ink-quiet">{playlist.description}</p>

      <div className="mt-auto flex w-full items-center justify-between border-t border-divider pt-s3">
        <span className="text-xs text-ink-muted">
          {count === 0 ? 'No tracks yet' : `${count} track${count !== 1 ? 's' : ''}`}
        </span>
        <KeyStrip camelots={camelots} />
      </div>
    </button>
  )
}

export default function Collections() {
  const navigate = useNavigate()

  return (
    <div className="mx-auto max-w-dense px-s4 pb-s6 pt-s5 sm:px-s6">
      <div className="mb-s5 border-b border-line-strong pb-s4">
        <h1 className="font-display text-[clamp(36px,6vw,56px)] font-light leading-none text-ink">
          Collections
        </h1>
        <p className="mt-s3 max-w-[660px] text-base text-ink-quiet">
          Hand-picked, not machine-found. Six sets are named and waiting for records.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-[22px] sm:grid-cols-2 lg:grid-cols-3">
        {PLAYLISTS.map(playlist => (
          <PlaylistCard
            key={playlist.id}
            playlist={playlist}
            onClick={() => navigate(`/collections/${playlist.id}`)}
          />
        ))}
      </div>

      <p className="mt-s5 text-sm italic text-ink-quiet">
        The strip fills in as tracks are added — twelve ticks, one per wheel position, so a
        collection's harmonic spread reads at a glance.
      </p>
    </div>
  )
}
