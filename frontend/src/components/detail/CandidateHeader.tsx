import type { Candidate } from '@/store/types';

interface CandidateHeaderProps {
  candidate: Candidate;
}

export function CandidateHeader({ candidate }: CandidateHeaderProps) {
  return (
    <div>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-heading text-2xl uppercase tracking-brutal text-foreground">
            {candidate.name}
          </h3>
          <p className="text-sm text-muted-foreground mt-sp-1">
            {candidate.title}
          </p>
        </div>
        <a
          href="#"
          className="text-info underline text-small font-mono hover:text-foreground transition-colors"
        >
          ↗ PDF
        </a>
      </div>
      <div className="flex flex-wrap gap-sp-3 mt-sp-2 text-tiny font-mono text-muted-foreground">
        <span>📍 {candidate.location}</span>
        <span>📧 {candidate.email}</span>
        <span>📞 {candidate.phone}</span>
      </div>
    </div>
  );
}
