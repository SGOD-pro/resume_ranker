import { NavLink } from 'react-router-dom';

export function AppHeader() {
  return (
    <header className="flex h-14 items-center justify-between border-b-thick border-border bg-card px-sp-4">
      <div className="flex items-center gap-8">
        <div className="flex flex-col justify-center">
          <span className="text-[9px] font-bold text-muted-foreground tracking-[0.3em] uppercase leading-none mb-1 select-none">
            SWYRA
          </span>
          <h3 className="font-heading text-xl tracking-brutal uppercase text-foreground leading-none">
            Sortlist
          </h3>
        </div>
        
        <nav className="hidden md:flex items-center gap-4">
          <NavLink 
            to="/" 
            className={({ isActive }) => 
              `px-3 py-1 font-mono text-sm uppercase tracking-wider transition-all border-thick rounded-md ${
                isActive 
                  ? 'bg-foreground text-background border-foreground shadow-[2px_2px_0px_0px_rgba(0,0,0,0.2)]' 
                  : 'border-transparent text-muted-foreground hover:border-foreground/20 hover:text-foreground'
              }`
            }
          >
            Home
          </NavLink>
          
          <NavLink 
            to="/ats-checker" 
            className={({ isActive }) => 
              `px-3 py-1 font-mono text-sm uppercase tracking-wider transition-all border-thick rounded-md ${
                isActive 
                  ? 'bg-foreground text-background border-foreground shadow-[2px_2px_0px_0px_rgba(0,0,0,0.2)]' 
                  : 'border-transparent text-muted-foreground hover:border-foreground/20 hover:text-foreground'
              }`
            }
          >
            ATS Checker
          </NavLink>
        </nav>
      </div>

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
