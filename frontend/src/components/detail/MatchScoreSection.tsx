import { cn } from '@/lib/utils';
import type { Candidate, Signal } from '@/store/types';

const signalLabels: Record<Signal, { label: string; color: string }> = {
  strong: { label: '🟢 Strong Match', color: 'text-success' },
  good: { label: '🟡 Good Match', color: 'text-warning' },
  fair: { label: '🟠 Fair Match', color: 'text-warning' },
  knockout: { label: '🔴 Knockout', color: 'text-error' },
  processing: { label: '⏳ Processing', color: 'text-muted-foreground' },
  'parse-failed': { label: '⚠ Parse Failed', color: 'text-error' },
};

interface MatchScoreSectionProps {
  candidate: Candidate;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const getWidthClass = (v: number): string => {
    if (v >= 95) return 'w-[95%]';
    if (v >= 90) return 'w-[90%]';
    if (v >= 85) return 'w-[85%]';
    if (v >= 80) return 'w-4/5';
    if (v >= 70) return 'w-[70%]';
    if (v >= 60) return 'w-3/5';
    if (v >= 50) return 'w-1/2';
    if (v >= 40) return 'w-2/5';
    if (v >= 30) return 'w-[30%]';
    if (v >= 20) return 'w-1/5';
    if (v >= 10) return 'w-[10%]';
    if (v > 0) return 'w-[5%]';
    return 'w-0';
  };

  return (
    <div className="flex items-center gap-sp-2">
      <span className="w-24 text-tiny uppercase tracking-chip font-semibold shrink-0 text-muted-foreground">
        {label}
      </span>
      <div className="flex-1 h-3 bg-surface-sunken border-2 border-border">
        <div className={cn('h-full bg-foreground transition-all', getWidthClass(value))} />
      </div>
      <span className="w-12 text-right font-mono text-tiny font-bold text-foreground">{(value).toFixed(3)}%</span>
    </div>
  );
}

export function MatchScoreSection({ candidate }: MatchScoreSectionProps) {
  const signal = signalLabels[candidate.signal];

  const getOverallWidthClass = (v: number): string => {
    if (v >= 95) return 'w-[95%]';
    if (v >= 90) return 'w-[90%]';
    if (v >= 85) return 'w-[85%]';
    if (v >= 80) return 'w-4/5';
    if (v >= 70) return 'w-[70%]';
    if (v >= 60) return 'w-3/5';
    if (v >= 50) return 'w-1/2';
    if (v >= 40) return 'w-2/5';
    if (v >= 30) return 'w-[30%]';
    if (v >= 20) return 'w-1/5';
    if (v >= 10) return 'w-[10%]';
    if (v > 0) return 'w-[5%]';
    return 'w-0';
  };

  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Match Score
      </h4>

      <div className="text-center mb-sp-3">
        <span className="font-heading text-5xl text-foreground">{candidate.overallScore}%</span>
        <p className={cn('text-small font-semibold mt-sp-1', signal.color)}>
          {signal.label}
        </p>
      </div>

      <div className="h-4 bg-surface-sunken border-thick border-border mb-sp-4">
        <div
          className={cn('h-full bg-foreground transition-all', getOverallWidthClass(candidate.overallScore))}
        />
      </div>

      <div className="space-y-sp-2">
        <ScoreBar label="Skills" value={candidate.scoreBreakdown.skills} />
        <ScoreBar label="Experience" value={candidate.scoreBreakdown.experience} />
        <ScoreBar label="Keywords" value={candidate.scoreBreakdown.keywords} />
        <ScoreBar label="Education" value={candidate.scoreBreakdown.education} />
      </div>
    </div>
  );
}
