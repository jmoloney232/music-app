import { formatKey } from '../utils/camelot'
import Tag from './Tag'
import SpotifyButton from './SpotifyButton'

const VOCAL_LABEL = {
  instrumental: 'Instrumental',
  vocal:        'Vocal',
  ambiguous:    'Mixed',
}

const VOCAL_COLOR = {
  instrumental: 'text-sky-400 border-sky-400/30',
  vocal:        'text-pink-400 border-pink-400/30',
  ambiguous:    'text-yellow-400 border-yellow-400/30',
}

function cleanStyle(s) {
  const parts = s.split('---')
  return parts[parts.length - 1].trim()
}

export default function TrackRow({ track, rank, onClick, showStyles = false }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-surface border border-border rounded-lg px-4 py-3
                 hover:border-purple-primary transition-colors group flex items-center gap-3"
    >
      <span className="font-mono text-xs text-text-subtle w-6 text-right flex-shrink-0">{rank}</span>
      <div className="flex-1 min-w-0">
        <div className="font-body text-sm font-medium text-text-primary group-hover:text-white transition-colors truncate">
          {track.title}
        </div>
        <div className="font-body text-xs text-text-secondary truncate mt-0.5">{track.artist}</div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className={`flex gap-1.5 ${showStyles ? 'flex-wrap justify-end max-w-[260px]' : ''}`}>
          {track.bpm    && <Tag color="text-sky-400 border-sky-400/30">{track.bpm} BPM</Tag>}
          {track.camelot && <Tag color="text-emerald-400 border-emerald-400/30">{formatKey(track.camelot)}</Tag>}
          {showStyles && track.vocal_class && (
            <Tag color={VOCAL_COLOR[track.vocal_class]}>
              {VOCAL_LABEL[track.vocal_class]}
            </Tag>
          )}
          {showStyles && (track.styles ?? []).slice(0, 2).map(s => (
            <Tag key={s}>{cleanStyle(s)}</Tag>
          ))}
        </div>
        <SpotifyButton artist={track.artist} title={track.title} />
      </div>
    </button>
  )
}
