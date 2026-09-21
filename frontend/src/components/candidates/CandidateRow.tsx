import { cn } from '@/lib/utils';
import { useCandidateStore } from '@/store/candidate-store';
import type { Candidate, Signal } from '@/store/types';

const signalConfig: Record<Signal, { label: string; color: string; dot: string }> = {
  strong: { label: 'Strong', color: 'text-success', dot: 'bg-success' },
  good: { label: 'Good', color: 'text-warning', dot: 'bg-warning' },
  fair: { label: 'Fair', color: 'text-warning', dot: 'bg-warning' },
  knockout: { label: 'Criteria Not Met', color: 'text-error', dot: 'bg-error' },
  processing: { label: 'Processing', color: 'text-muted-foreground', dot: 'bg-muted-foreground' },
  'parse-failed': { label: 'Failed', color: 'text-error', dot: 'bg-error' },
};

interface CandidateRowProps {
  candidate: Candidate;
}

export function CandidateRow({ candidate }: CandidateRowProps) {
  const { selectedId, selectCandidate } = useCandidateStore();
  const isSelected = selectedId === candidate.id;
  const signal = signalConfig[candidate.signal];

  const isUnresolvedName =
    candidate.name === 'Name needs review' ||
    candidate.identityStatus === 'UNRESOLVED' ||
    !candidate.name;
  const displayName = isUnresolvedName ? 'Name needs review' : candidate.name;

  const scoreValue = candidate.relevanceScore ?? candidate.overallScore;

  // Derive eligibility badge
  const eligibility = candidate.eligibilityStatus || (candidate.signal === 'knockout' ? 'DOES_NOT_MEET_CRITERIA' : 'ELIGIBLE');
  let statusBadge = {
    label: signal.label,
    color: signal.color,
    dot: signal.dot,
  };

  if (eligibility === 'DOES_NOT_MEET_CRITERIA') {
    statusBadge = {
      label: 'Criteria Not Met',
      color: 'text-error',
      dot: 'bg-error',
    };
  } else if (eligibility === 'REVIEW_REQUIRED') {
    statusBadge = {
      label: 'Review Required',
      color: 'text-warning',
      dot: 'bg-warning',
    };
  }

  return (
    <button
      data-testid="candidate-row"
      onClick={() => selectCandidate(candidate.id)}
      className={cn(
        'w-full text-left border-b border-border px-sp-4 py-sp-2 transition-colors cursor-pointer',
        isSelected
          ? 'bg-foreground text-background'
          : 'bg-background text-foreground hover:bg-secondary'
      )}
    >
      {/* Top row */}
      <div className="flex items-center gap-sp-2">
        <span className="w-8 font-mono text-small font-bold">
          {candidate.rank}
        </span>
        <div className="flex-1 truncate flex items-center gap-1.5">
          {isUnresolvedName ? (
            <span
              className={cn(
                'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-medium border',
                isSelected
                  ? 'bg-warning/20 text-warning-foreground border-warning/40'
                  : 'bg-warning/10 text-warning border-warning/30'
              )}
            >
              <span aria-hidden="true">⚠</span>
              {displayName}
            </span>
          ) : (
            <span className="font-semibold text-sm truncate">{displayName}</span>
          )}
        </div>
        <span className="w-16 text-right font-mono text-sm font-bold">
          {scoreValue}%
        </span>
        <span
          className={cn(
            'w-28 text-right text-xs uppercase tracking-chip font-bold flex items-center justify-end gap-1',
            isSelected ? 'text-current' : statusBadge.color
          )}
        >
          <span className={cn('inline-block w-2 h-2 rounded-full', isSelected ? 'bg-current' : statusBadge.dot)} />
          {statusBadge.label}
        </span>
      </div>

      {/* Skills line */}
      <div className="ml-8 mt-sp-1">
        <p className={cn('text-sm font-mono', isSelected ? 'opacity-80' : 'text-muted-foreground')}>
          {candidate.topSkills.join(' · ')}
        </p>
      </div>

      {/* Flags */}
      {candidate.flags.length > 0 && (
        <div className="ml-8 mt-sp-1">
          {candidate.flags.map((flag, i) => (
            <p
              key={i}
              className={cn(
                'text-sm',
                isSelected
                  ? 'opacity-70'
                  : flag.type === 'warning'
                    ? 'text-warning'
                    : 'text-muted-foreground'
              )}
            >
              {flag.type === 'warning' ? '⚠' : 'ℹ'} {flag.message}
            </p>
          ))}
        </div>
      )}
    </button>
  );
}
