import type { Candidate } from '@/store/types';
import { MapPin,MailIcon,PhoneIcon } from 'lucide-react';

interface CandidateHeaderProps {
  candidate: Candidate;
}

export function CandidateHeader({ candidate }: CandidateHeaderProps) {
  const hasContactInfo = candidate.location || candidate.email || candidate.phone;

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
        {candidate.pdfUrl ? (
          <a
            href={candidate.pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-info underline text-small font-mono hover:text-foreground transition-colors"
          >
            ↗ PDF
          </a>
        ) : (
          <span className="text-muted-foreground/50 text-small font-mono">
            No PDF
          </span>
        )}
      </div>
      {hasContactInfo && (
        <div className="flex flex-wrap gap-sp-3 mt-sp-2 text-tiny font-mono text-muted-foreground">
          {candidate.location && <span className='flex items-center gap-2'><MapPin size={15}/> {candidate.location}</span>}
          {candidate.email && (
            <a
              href={`mailto:${candidate.email}`}
              className="hover:text-foreground transition-colors flex items-center gap-2"
            >
              <MailIcon size={15}/> <span className='underline'>{candidate.email}</span>
            </a>
          )}
          {candidate.phone && (
            <a
              href={`tel:${candidate.phone}`}
              className="hover:text-foreground transition-colors flex items-center gap-2"
            >
              <PhoneIcon size={15}/> {candidate.phone}
            </a>
          )}
        </div>
      )}
    </div>
  );
}
