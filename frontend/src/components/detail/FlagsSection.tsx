import type { CandidateFlag } from '@/store/types';

interface FlagsSectionProps {
  flags: CandidateFlag[];
}

export function FlagsSection({ flags }: FlagsSectionProps) {
  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Flags
      </h4>
      <div className="space-y-sp-2">
        {flags.map((flag, i) => (
          <div
            key={i}
            className={
              flag.type === 'warning'
                ? 'border-2 border-warning p-sp-2 text-warning text-small font-semibold'
                : 'border-2 border-info p-sp-2 text-info text-small font-semibold'
            }
          >
            {flag.type === 'warning' ? '⚠' : 'ℹ'} {flag.message}
          </div>
        ))}
      </div>
    </div>
  );
}
