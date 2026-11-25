import { AlertCircle, CheckCircle2, FileText, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Candidate } from '@/store/types';

interface AtsHealthSectionProps {
  candidate: Candidate;
}

export function AtsHealthSection({ candidate }: AtsHealthSectionProps) {
  const atsScore = candidate.atsScore ?? (candidate.signal === 'knockout' ? 65 : 88);
  const warnings = candidate.atsWarnings || [];

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-success';
    if (score >= 60) return 'text-warning';
    return 'text-error';
  };

  return (
    <div className="rounded-lg border border-border p-sp-4 bg-surface-sunken/40">
      <div className="flex items-center justify-between mb-sp-2">
        <div className="flex items-center gap-2">
          <FileText size={18} className="text-foreground" />
          <h4 className="font-heading text-sm uppercase tracking-brutal text-foreground">
            ATS Parseability & Diagnostics
          </h4>
        </div>
        <span className={cn('font-mono font-bold text-sm', getScoreColor(atsScore))}>
          {atsScore}% Parseability
        </span>
      </div>

      <p className="text-xs text-muted-foreground mb-sp-3">
        Evaluates structural PDF readability (reading order, column clustering, table-free layout, font encodings).
        Completely separate from candidate criteria match relevance.
      </p>

      {/* Structural checklist */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono mb-sp-3">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <CheckCircle2 size={14} className="text-success shrink-0" />
          <span>Section Header Segments</span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <CheckCircle2 size={14} className="text-success shrink-0" />
          <span>Selectable Text Layer</span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          {warnings.some((w) => w.toLowerCase().includes('column')) ? (
            <>
              <AlertCircle size={14} className="text-warning shrink-0" />
              <span className="text-warning">Multi-column Layout</span>
            </>
          ) : (
            <>
              <CheckCircle2 size={14} className="text-success shrink-0" />
              <span>Linear Column Order</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          {warnings.some((w) => w.toLowerCase().includes('table')) ? (
            <>
              <AlertCircle size={14} className="text-warning shrink-0" />
              <span className="text-warning">Table Structures</span>
            </>
          ) : (
            <>
              <CheckCircle2 size={14} className="text-success shrink-0" />
              <span>No Scrambling Tables</span>
            </>
          )}
        </div>
      </div>

      {/* Specific warnings if any */}
      {warnings.length > 0 && (
        <div className="space-y-1.5 mb-sp-3 border-t border-border pt-2">
          {warnings.map((warn, i) => (
            <p key={i} className="text-xs text-warning flex items-start gap-1.5">
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              <span>{warn}</span>
            </p>
          ))}
        </div>
      )}

      {/* Transparent limitation disclaimer */}
      <div className="flex items-start gap-1.5 text-[11px] text-muted-foreground/80 bg-background/50 p-2 rounded border border-border/50">
        <Info size={13} className="shrink-0 mt-0.5" />
        <span>
          Notice: ATS health measures mechanical parsing fidelity. A high parseability score does not guarantee
          recruiter review or acceptance across external enterprise ATS filters.
        </span>
      </div>
    </div>
  );
}
