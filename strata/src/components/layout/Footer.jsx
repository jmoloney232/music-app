export default function Footer() {
  return (
    <footer className="border-t border-hairline bg-canvas">
      <div className="mx-auto flex max-w-dense flex-wrap items-center justify-between gap-s2 px-s4 py-s4 sm:px-s5">
        <span className="text-xs uppercase tracking-[0.18em] text-ink-quiet">
          Similar Song Search
        </span>
        <span className="text-xs text-ink-muted">
          Similarity from audio embeddings · {new Date().getFullYear()}
        </span>
      </div>
    </footer>
  )
}
