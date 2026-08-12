import { formatKey } from '../utils/camelot'
import Tag from './Tag'
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

// Bar length carries the value; the number is always spelled out beside it.
// Only the top tier gets extra typographic weight, so nothing rests on colour alone.
// The grow animation is CSS keyed on the value, so no state or effect is needed
// to replay it when the score changes.
function ScoreBar({ score }) {
  const pct = Math.round(score * 100)

  return (
    <div className="flex items-center gap-s2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
        <div
          key={pct}
          className="score-fill h-full rounded-full bg-accent"
          style={{ '--score-width': `${pct}%` }}
        />
      </div>
      <span
        className={`w-9 text-right font-mono text-xs tabular-nums ${
          pct >= 80 ? 'font-medium text-ink' : 'text-ink-quiet'
        }`}
      >
        {pct}%
      </span>
    </div>
  )
}

export function TrackMeta({
  track,
  styleLimit = 2,
  compatible = null,
  showStyles = true,
  align = 'start',
}) {
  const isCompatible = compatible != null && track.camelot != null && compatible.has(track.camelot)

  return (
    <div className={`flex flex-wrap gap-1.5 ${align === 'end' ? 'md:justify-end' : ''}`}>
      {track.bpm && <Tag>{track.bpm} BPM</Tag>}
      {track.camelot && (
        <Tag camelot={track.camelot} compatible={isCompatible}>
          {formatKey(track.camelot)}
        </Tag>
      )}
      {showStyles && track.vocal_class && (
        <Tag variant="label">{VOCAL_LABEL[track.vocal_class] ?? track.vocal_class}</Tag>
      )}
      {showStyles &&
        (track.styles ?? []).slice(0, styleLimit).map(s => (
          <Tag key={s} variant="label">{cleanStyle(s)}</Tag>
        ))}
    </div>
  )
}

/**
 * The single track row for every list in the app. `score` opts into the
 * similarity column (Results); `compatible` is the query's compatible-key Set,
 * which marks the rows a DJ can actually mix into.
 *
 * Grid rather than nested flex so rank ordinals and percentages line up as real
 * columns down a long list — auto/fixed tracks size against every row, not each
 * row on its own.
 */
export default function TrackRow({
  track,
  rank,
  onClick,
  score = null,
  compatible = null,
  showStyles = false,
  // One style, not two: a second tag pushes the metadata onto a second line on
  // the busiest rows, and rows of unequal height are what makes a 50-row list
  // hard to scan. The full style list is on the track's own results page.
  styleLimit = 1,
}) {
  const cols = score != null
    ? 'md:grid-cols-[2rem_minmax(0,1fr)_auto_9rem_1.75rem]'
    : 'md:grid-cols-[2rem_minmax(0,1fr)_auto_1.75rem]'

  return (
    <div
      className={`group relative grid grid-cols-[2rem_minmax(0,1fr)_1.75rem] items-center gap-x-s3
                  gap-y-s2 rounded border border-hairline bg-surface px-s3 py-2.5
                  transition-colors hover:border-line-strong hover:bg-sunken
                  focus-within:border-accent ${cols}`}
    >
      <span className="self-start font-mono text-xs tabular-nums text-ink-muted md:self-center md:text-right">
        {rank}
      </span>

      <div className="min-w-0">
        <button
          onClick={onClick}
          className="block w-full truncate text-left text-sm font-medium text-ink
                     after:absolute after:inset-0 after:content-['']"
        >
          {track.title}
        </button>
        <div className="truncate text-xs text-ink-quiet">{track.artist}</div>
      </div>

      {/* Mobile: tags drop to their own line under the title, spanning the text column. */}
      <div className="col-span-2 col-start-2 md:col-span-1 md:col-start-auto md:max-w-[380px]">
        <TrackMeta
          track={track}
          compatible={compatible}
          showStyles={showStyles}
          styleLimit={styleLimit}
          align="end"
        />
      </div>

      {score != null && (
        <div className="col-span-2 col-start-2 md:col-span-1 md:col-start-auto">
          <ScoreBar score={score} />
        </div>
      )}

      <div className="col-start-3 row-start-1 justify-self-end md:col-start-auto md:row-start-auto">
        <SpotifyButton artist={track.artist} title={track.title} />
      </div>
    </div>
  )
}
