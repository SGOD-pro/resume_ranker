export function AppHeader() {
  return (
    <header className="flex h-14 items-center justify-between border-b-thick border-border bg-card px-sp-4">
      <h3 className="font-heading text-xl tracking-brutal uppercase text-foreground">
        AI Resume Screener
      </h3>
      <div className="flex items-center gap-sp-2">
        <button
          className="flex h-9 w-9 items-center justify-center border-thick border-foreground text-foreground uppercase tracking-brutal text-small hover:bg-foreground hover:text-background transition-colors"
          aria-label="Settings"
        >
          ⚙
        </button>
        <button
          className="flex h-9 w-9 items-center justify-center border-thick border-foreground text-foreground uppercase tracking-brutal text-small hover:bg-foreground hover:text-background transition-colors"
          aria-label="Help"
        >
          ?
        </button>
      </div>
    </header>
  );
}
