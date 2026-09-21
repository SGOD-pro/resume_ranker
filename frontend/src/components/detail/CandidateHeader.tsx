import { useState } from 'react';
import type { Candidate } from '@/store/types';
import { MapPin, MailIcon, PhoneIcon, HelpCircle, ShieldCheck, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

interface CandidateHeaderProps {
  candidate: Candidate;
}

export function CandidateHeader({ candidate }: CandidateHeaderProps) {
  const [open, setOpen] = useState(false);
  const hasContactInfo = candidate.location || candidate.email || candidate.phone;

  const isUnresolved =
    candidate.name === 'Name needs review' ||
    candidate.identityStatus === 'UNRESOLVED' ||
    !candidate.name;

  const prov = candidate.identityProvenance || {};
  const status = candidate.identityStatus || (isUnresolved ? 'UNRESOLVED' : 'VERIFIED');
  const confidencePct = Math.round((candidate.identityConfidence ?? (isUnresolved ? 0 : 1)) * 100);
  const rejections = Array.isArray(prov.candidate_rejections) ? prov.candidate_rejections : [];

  return (
    <div>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-2xl uppercase tracking-brutal text-foreground">
              {candidate.name}
            </h3>

            {isUnresolved && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-bold bg-warning/15 text-warning border border-warning/30">
                <AlertTriangle size={13} />
                Unresolved Identity
              </span>
            )}

            {/* Why this name dialog */}
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs font-mono text-muted-foreground hover:text-foreground border border-border px-2 py-0.5 rounded transition-colors cursor-pointer bg-secondary/50"
                  title="View name resolution evidence and provenance"
                >
                  <HelpCircle size={13} />
                  Why this name?
                </button>
              </DialogTrigger>

              <DialogContent className="max-w-md bg-background border-2 border-border text-foreground">
                <DialogHeader>
                  <DialogTitle className="font-heading uppercase tracking-brutal text-lg flex items-center gap-2">
                    <ShieldCheck size={18} className="text-primary" />
                    Identity Resolution Evidence
                  </DialogTitle>
                </DialogHeader>

                <div className="space-y-3 text-xs font-mono pt-2">
                  <div className="flex justify-between items-center border-b border-border pb-2">
                    <span className="text-muted-foreground">Status:</span>
                    <span
                      className={cn(
                        'px-2 py-0.5 rounded font-bold uppercase',
                        status === 'VERIFIED'
                          ? 'bg-success/20 text-success'
                          : status === 'PLAUSIBLE'
                            ? 'bg-info/20 text-info'
                            : 'bg-warning/20 text-warning'
                      )}
                    >
                      {status}
                    </span>
                  </div>

                  <div className="flex justify-between items-center border-b border-border pb-2">
                    <span className="text-muted-foreground">Confidence:</span>
                    <span className="font-bold">{confidencePct}%</span>
                  </div>

                  <div className="flex justify-between items-center border-b border-border pb-2">
                    <span className="text-muted-foreground">Source:</span>
                    <span className="font-bold">{String(prov.source || 'Deterministic Header Analysis')}</span>
                  </div>

                  {Boolean(prov.page) && (
                    <div className="flex justify-between items-center border-b border-border pb-2">
                      <span className="text-muted-foreground">Document Location:</span>
                      <span>
                        Page {String(prov.page)}{' '}
                        {Array.isArray(prov.bounding_box)
                          ? `(${prov.bounding_box.map((n: number) => Math.round(n)).join(', ')})`
                          : ''}
                      </span>
                    </div>
                  )}

                  {Boolean(prov.evidence_text) && (
                    <div className="border-b border-border pb-2">
                      <span className="text-muted-foreground block mb-1">Supporting Evidence Text:</span>
                      <p className="p-2 rounded bg-surface-sunken border border-border text-foreground font-mono text-[11px] break-words">
                        "{String(prov.evidence_text)}"
                      </p>
                    </div>
                  )}

                  {rejections.length > 0 && (
                    <div className="border-b border-border pb-2">
                      <span className="text-muted-foreground block mb-1">Rejected False Proposals:</span>
                      <ul className="space-y-1 text-warning text-[11px]">
                        {rejections.map((rej: unknown, i: number) => {
                          const text = typeof rej === 'string'
                            ? rej
                            : typeof rej === 'object' && rej !== null && 'text' in rej
                              ? `${String((rej as Record<string, unknown>).text)} (${String((rej as Record<string, unknown>).reason || '')})`
                              : String(rej);
                          return (
                            <li key={i} className="flex items-start gap-1">
                              <span>✕</span>
                              <span>{text}</span>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  )}

                  <div className="p-2 rounded bg-surface-sunken/60 text-[11px] text-muted-foreground border border-border/50">
                    Rule Guardrail: Descriptive phrases, job titles, sentence fragments, and skill lists
                    are strictly prohibited from being displayed as candidate identities. If confidence is below threshold,
                    the candidate is marked as "Name needs review".
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>

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
          {candidate.location && (
            <span className="flex items-center gap-2">
              <MapPin size={15} /> {candidate.location}
            </span>
          )}
          {candidate.email && (
            <a
              href={`mailto:${candidate.email}`}
              className="hover:text-foreground transition-colors flex items-center gap-2"
            >
              <MailIcon size={15} /> <span className="underline">{candidate.email}</span>
            </a>
          )}
          {candidate.phone && (
            <a
              href={`tel:${candidate.phone}`}
              className="hover:text-foreground transition-colors flex items-center gap-2"
            >
              <PhoneIcon size={15} /> {candidate.phone}
            </a>
          )}
        </div>
      )}
    </div>
  );
}
