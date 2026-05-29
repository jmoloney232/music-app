export default function Footer() {
  return (
    <footer className="border-t border-border bg-surface px-8 py-6 flex items-center justify-between">
      <span className="font-headline font-bold text-sm tracking-widest text-text-primary">STRATA</span>
      <span className="text-text-secondary text-xs font-body">© {new Date().getFullYear()} Strata</span>
    </footer>
  )
}
