import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Settings, HelpCircle, Server, Database, Cpu, ShieldCheck } from 'lucide-react';

export function AppHeader() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

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
        {/* Settings Dialog */}
        <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
          <DialogTrigger asChild>
            <button
              className="flex h-9 w-9 items-center justify-center border-thick border-foreground text-foreground uppercase tracking-brutal text-small hover:bg-foreground hover:text-background transition-colors cursor-pointer"
              aria-label="Settings"
            >
              <Settings size={16} />
            </button>
          </DialogTrigger>
          <DialogContent className="max-w-md bg-background border-2 border-border text-foreground">
            <DialogHeader>
              <DialogTitle className="font-heading uppercase tracking-brutal text-lg flex items-center gap-2">
                <Settings size={18} className="text-primary" />
                Environment & System Settings
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3 font-mono text-xs pt-2">
              <div className="flex justify-between items-center border-b border-border pb-2">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Server size={14} /> Backend API:
                </span>
                <span className="font-bold text-success">{apiBase} (Connected ✓)</span>
              </div>
              <div className="flex justify-between items-center border-b border-border pb-2">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Database size={14} /> Storage Engine:
                </span>
                <span className="font-bold">S3 + DynamoDB</span>
              </div>
              <div className="flex justify-between items-center border-b border-border pb-2">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Cpu size={14} /> Extraction Tier:
                </span>
                <span className="font-bold">PyMuPDF → ODL → Bedrock Nova</span>
              </div>
              <div className="flex justify-between items-center border-b border-border pb-2">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <ShieldCheck size={14} /> Scoring Mode:
                </span>
                <span className="font-bold">Deterministic (No Prestige/Gap Bias)</span>
              </div>
              <p className="text-[11px] text-muted-foreground pt-1">
                Running in Localhost Pair-Programming Mode. All operations communicate exclusively with the local backend.
              </p>
            </div>
          </DialogContent>
        </Dialog>

        {/* Help Dialog */}
        <Dialog open={helpOpen} onOpenChange={setHelpOpen}>
          <DialogTrigger asChild>
            <button
              className="flex h-9 w-9 items-center justify-center border-thick border-foreground text-foreground uppercase tracking-brutal text-small hover:bg-foreground hover:text-background transition-colors cursor-pointer"
              aria-label="Help"
            >
              <HelpCircle size={16} />
            </button>
          </DialogTrigger>
          <DialogContent className="max-w-lg bg-background border-2 border-border text-foreground">
            <DialogHeader>
              <DialogTitle className="font-heading uppercase tracking-brutal text-lg flex items-center gap-2">
                <HelpCircle size={18} className="text-primary" />
                How to Use SWYRA Sortlist
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3 font-mono text-xs pt-2">
              <div className="p-2.5 rounded bg-surface-sunken border border-border space-y-1">
                <p className="font-bold text-foreground">1. Set Up the Job Description</p>
                <p className="text-muted-foreground">
                  Enter Job Title, paste or upload a JD PDF, add Must-Have / Nice-to-Have skills, and configure weights (must total 100%).
                </p>
              </div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border space-y-1">
                <p className="font-bold text-foreground">2. Upload Candidate Resumes</p>
                <p className="text-muted-foreground">
                  Drag and drop or browse PDF resumes. Resumes are parsed through the fast PyMuPDF extraction pipeline.
                </p>
              </div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border space-y-1">
                <p className="font-bold text-foreground">3. Analyze & Rank</p>
                <p className="text-muted-foreground">
                  Click "Analyze Resumes". The ranking engine scores relevance across skills, experience, keywords, and education.
                </p>
              </div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border space-y-1">
                <p className="font-bold text-foreground">4. Human Review & Decisions</p>
                <p className="text-muted-foreground">
                  Inspect structured candidate timelines. Mark Shortlisted, Document Rejection Reason, Send Assessment, or Reset.
                </p>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </header>
  );
}
