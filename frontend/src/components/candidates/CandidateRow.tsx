import { cn } from '@/lib/utils';
import { useCandidateStore } from '@/store/candidate-store';
import type { Candidate, Signal } from '@/store/types';

const signalConfig: Record<Signal, { label: string; color: string; dot: string }> = {
  strong: { label: 'Strong', color: 'text-success', dot: 'bg-success' },
  good: { label: 'Good', color: 'text-warning', dot: 'bg-warning' },
  fair: { label: 'Fair', color: 'text-warning', dot: 'bg-warning' },
  knockout: { label: 'Knockout', color: 'text-error', dot: 'bg-error' },
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

  return (
    <button
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
        <span className="flex-1 font-semibold text-sm truncate">
          {candidate.name}
        </span>
        <span className="w-16 text-right font-mono text-sm font-bold">
          {candidate.overallScore}%
        </span>
        <span
          className={cn(
            'w-20 text-right text-sm uppercase tracking-chip font-bold flex items-center justify-end gap-1',
            isSelected ? 'text-current' : signal.color
          )}
        >
          <span className={cn('inline-block w-2 h-2 rounded-full', isSelected ? 'bg-current' : signal.dot)} />
          {signal.label}
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
