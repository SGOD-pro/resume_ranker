/**
 * ColdStartLoader.tsx — Full-page "waking up" overlay
 * =====================================================
 * Shown when the backend is slow to respond (Lambda cold start).
 * Copy says "waking up" — not "error" or "something broke."
 * This is EXPECTED behavior for serverless backends.
 */

import { Spinner } from '@/components/ui/spinner';

export function ColdStartLoader() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-sp-4 text-center">
        {/* Pulsing logo / title */}
        <h3 className="font-heading text-2xl uppercase tracking-brutal text-foreground animate-cold-start-pulse">
          AI Resume Screener
        </h3>

        {/* Spinner */}
        <Spinner className="size-8 text-foreground" />

        {/* Reassuring copy */}
        <div className="space-y-sp-1">
          <p className="text-small font-bold uppercase tracking-brutal text-foreground">
            Waking Up
          </p>
          <p className="text-tiny text-muted-foreground font-mono max-w-xs">
            Our backend is starting up — this is normal and usually takes a few seconds.
          </p>
        </div>

        {/* Animated dots */}
        <div className="flex gap-sp-1">
          <span className="inline-block w-2 h-2 bg-foreground animate-cold-start-dot1" />
          <span className="inline-block w-2 h-2 bg-foreground animate-cold-start-dot2" />
          <span className="inline-block w-2 h-2 bg-foreground animate-cold-start-dot3" />
        </div>
      </div>
    </div>
  );
}
