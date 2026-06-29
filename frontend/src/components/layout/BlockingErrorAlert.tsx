/**
 * BlockingErrorAlert.tsx — Full-page blocking error overlay
 * ===========================================================
 * Driven by appStore.blockingError. When non-null, shows a
 * full-screen overlay with a shadcn Alert — the user MUST
 * acknowledge / retry. There's no "dismiss" — the error is
 * blocking because continuing would show stale/wrong data.
 *
 * Used for:
 * - Backend unreachable (3 health retries exhausted)
 * - Scoring endpoint 500 / weights validation
 * - SSE drops after 3 reconnection attempts
 */

import { AlertCircle } from 'lucide-react';
import { Alert, AlertTitle, AlertDescription, AlertAction } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/app-store';

export function BlockingErrorAlert() {
  const blockingError = useAppStore((s) => s.blockingError);
  const setBlockingError = useAppStore((s) => s.setBlockingError);

  if (!blockingError) return null;

  const handleRetry = () => {
    if (blockingError.onRetry) {
      setBlockingError(null);
      blockingError.onRetry();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/90">
      <div className="w-full max-w-md px-sp-4">
        <Alert
          variant="destructive"
          className="border-thick border-error bg-card p-sp-4"
        >
          <AlertCircle className="size-5" />
          <AlertTitle className="font-heading text-base uppercase tracking-brutal">
            {blockingError.title}
          </AlertTitle>
          <AlertDescription className="font-mono text-xs leading-tight">
            {blockingError.message}
          </AlertDescription>
          {blockingError.onRetry && (
            <div className="mt-sp-2 col-2 justify-end flex">
              <Button
                onClick={handleRetry}
                className="h-10 bg-foreground text-background border-thick border-foreground uppercase tracking-brutal text-sm font-bold hover:bg-background hover:text-foreground transition-colors"
              >
                Retry
              </Button>
            </div>
          )}
        </Alert>
      </div>
    </div>
  );
}
