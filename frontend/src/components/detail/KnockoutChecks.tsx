import { cn } from '@/lib/utils';
import type { KnockoutCheck } from '@/store/types';

interface KnockoutChecksProps {
  checks: KnockoutCheck[];
}

export function KnockoutChecks({ checks }: KnockoutChecksProps) {
  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Knockout Checks
      </h4>
      <div className="space-y-sp-2">
        {checks.map((check, i) => (
          <div
            key={i}
            className={cn(
              'flex items-center gap-sp-2 p-sp-2 border-2',
              check.passed ? 'border-success' : 'border-error'
            )}
          >
            <span className="text-base font-bold shrink-0">
              {check.passed ? '✅' : '❌'}
            </span>
            <span className="text-small font-semibold flex-1 text-foreground">
              {check.label}
            </span>
            <span className="text-tiny font-mono text-muted-foreground">
              → {check.detail}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
