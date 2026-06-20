/**
 * CenterPanelLoader.tsx — Extraction / Scoring phase loader
 * ===========================================================
 * Replaces the candidate list content area ONLY during
 * extraction and scoring phases. The upload zone, filters,
 * and header remain visible/interactive.
 *
 * Two modes with different messages per Phase 0 table:
 * - extracting: "Extracting resume data…"
 * - scoring:    "Scoring & ranking candidates…"
 */

import { Spinner } from '@/components/ui/spinner';
import type { AppPhase } from '@/store/app-store';
import { useAppStore } from '@/store/app-store';

const phaseConfig: Record<string, { title: string; subtitle: string }> = {
  extracting: {
    title: 'Extracting Resume Data',
    subtitle: 'Parsing PDFs and extracting structured information…',
  },
  scoring: {
    title: 'Scoring & Ranking Candidates',
    subtitle: 'Applying weights and computing match scores…',
  },
};

interface CenterPanelLoaderProps {
  phase: AppPhase;
}

export function CenterPanelLoader({ phase }: CenterPanelLoaderProps) {
  const sseRetryCount = useAppStore((s) => s.sseRetryCount);
  const config = phaseConfig[phase];

  if (!config) return null;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-sp-5 gap-sp-4">
      {/* Main spinner and message */}
      <div className="flex flex-col items-center gap-sp-3 text-center">
        <Spinner className="size-8 text-foreground" />

        <h4 className="font-heading text-lg uppercase tracking-brutal text-foreground">
          {config.title}
        </h4>

        <p className="text-tiny font-mono text-muted-foreground max-w-xs">
          {config.subtitle}
        </p>
      </div>

      {/* SSE reconnecting indicator */}
      {phase === 'extracting' && sseRetryCount > 0 && (
        <div className="flex items-center gap-sp-2 border-thick border-warning bg-card px-sp-3 py-sp-2">
          <span className="inline-block w-2 h-2 bg-warning animate-pulse" />
          <span className="text-tiny font-mono font-bold text-warning uppercase tracking-chip">
            Reconnecting… (attempt {sseRetryCount}/3)
          </span>
        </div>
      )}

      {/* Animated progress dots */}
      <div className="flex gap-sp-1 mt-sp-2">
        <span className="inline-block w-2 h-2 bg-foreground animate-cold-start-dot1" />
        <span className="inline-block w-2 h-2 bg-foreground animate-cold-start-dot2" />
        <span className="inline-block w-2 h-2 bg-foreground animate-cold-start-dot3" />
      </div>
    </div>
  );
}
