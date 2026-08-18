import { shortKeyName } from '../utils/camelot'
import SpotifyButton from './SpotifyButton'

const VOCAL_LABEL = {
  instrumental: 'Instrumental',
  vocal:        'Vocal',
  ambiguous:    'Mixed',
}

function cleanStyle(s) {
  const parts = s.split('---')
  return parts[parts.length - 1].trim()
}

/**
 * The catalogue-table row used by Explore and collection lists. Booth renders
 * these as ruled table rows — title in display type, figures in tabular Lora —
 * rather than bordered cards. Fixed column tracks on desktop so figures align
 * down a 50-row page; on mobile the metadata wraps under the title.
 */
export default function TrackRow({ track, onClick }) {
  const style = (track.styles ?? [])[0]

  return (
    <div
      className="group relative grid grid-cols-[minmax(0,1fr)_28px] items-baseline gap-x-s4 gap-y-1
                 border-b border-hairline py-[15px]
                 md:grid-cols-[minmax(0,1fr)_92px_130px_116px_140px_28px] md:gap-x-s4"
    >
      <div className="flex min-w-0 items-baseline gap-s3">
        <button
          onClick={onClick}
          className="min-w-0 truncate rounded text-left font-display text-[20px] leading-tight text-ink
                     transition-colors after:absolute after:inset-0 after:content-['']
                     group-hover:text-accent md:text-[24px]"
        >
          {track.title}
        </button>
        <span className="hidden truncate text-sm text-ink-quiet sm:inline">{track.artist}</span>
      </div>

      {/* Mobile: artist + metadata drop to their own line under the title. */}
      <div className="col-start-1 flex flex-wrap items-baseline gap-x-s3 text-sm tabular-nums text-ink-soft md:hidden">
        <span className="truncate text-ink-quiet sm:hidden">{track.artist}</span>
        {track.bpm != null && <span>{track.bpm.toFixed(1)}</span>}
        {track.camelot && <span>{track.camelot} · {shortKeyName(track.camelot)}</span>}
        {track.vocal_class && <span className="text-ink-quiet">{VOCAL_LABEL[track.vocal_class]}</span>}
      </div>

      <span className="hidden text-sm tabular-nums text-ink-soft md:inline">
        {track.bpm != null ? track.bpm.toFixed(1) : ''}
      </span>
      <span className="hidden text-sm tabular-nums text-ink-soft md:inline">
        {track.camelot ? `${track.camelot} · ${shortKeyName(track.camelot)}` : ''}
      </span>
      <span className="hidden text-sm text-ink-quiet md:inline">
        {track.vocal_class ? VOCAL_LABEL[track.vocal_class] : ''}
      </span>
      <span className="hidden truncate text-sm text-ink-quiet md:inline">
        {style ? cleanStyle(style) : ''}
      </span>

      <div className="col-start-2 row-start-1 justify-self-end md:col-start-auto md:row-start-auto">
        <SpotifyButton artist={track.artist} title={track.title} />
      </div>
    </div>
  )
}
