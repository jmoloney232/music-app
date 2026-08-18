export default function Footer() {
  return (
    <footer className="border-t border-divider bg-canvas">
      <div className="mx-auto flex max-w-dense flex-wrap items-center justify-between gap-s2 px-s4 py-s3 sm:px-s6">
        <span className="text-[11px] uppercase tracking-[0.12em] text-ink-muted">
          Similar Song Search · similarity from audio embeddings
        </span>
        <span className="text-[11px] uppercase tracking-[0.12em] text-ink-muted">
          Scores are relative, not absolute
        </span>
      </div>
    </footer>
  )
}
