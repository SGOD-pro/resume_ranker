/**
 * BackendHealthGate.tsx — Backend reachability wrapper
 * ======================================================
 * Wraps the entire app. On mount:
 * 1. Pings GET /health with 3s timeout
 * 2. If slow → shows ColdStartLoader ("waking up")
 * 3. Retries up to 3x with 2s backoff
 * 4. After 3 failures → sets blocking error (Alert)
 * 5. On success → renders children (the main app)
 */

import { useEffect, useCallback, useRef, type ReactNode } from 'react';
import { checkHealth } from '@/lib/api';
import { useAppStore } from '@/store/app-store';
import { ColdStartLoader } from './ColdStartLoader';

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

interface BackendHealthGateProps {
  children: ReactNode;
}

export function BackendHealthGate({ children }: BackendHealthGateProps) {
  const backendStatus = useAppStore((s) => s.backendStatus);
  const setBackendStatus = useAppStore((s) => s.setBackendStatus);
  const setBlockingError = useAppStore((s) => s.setBlockingError);
  const retryCountRef = useRef(0);

  const performHealthCheck = useCallback(async () => {
    retryCountRef.current = 0;
    setBackendStatus('checking');
    setBlockingError(null);

    while (retryCountRef.current < MAX_RETRIES) {
      try {
        await checkHealth();
        setBackendStatus('ready');
        return;
      } catch {
        retryCountRef.current++;

        if (retryCountRef.current === 1) {
          // First failure — show cold-start loader
          setBackendStatus('waking-up');
        }

        if (retryCountRef.current < MAX_RETRIES) {
          await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        }
      }
    }

    // All retries exhausted → unreachable
    setBackendStatus('unreachable');
    setBlockingError({
      title: 'Backend Unreachable',
      message:
        'Unable to connect to the server after multiple attempts. Please check that the backend is running and try again.',
      onRetry: () => performHealthCheck(),
    });
  }, [setBackendStatus, setBlockingError]);

  useEffect(() => {
    performHealthCheck();
  }, [performHealthCheck]);

  // Show cold-start loader while checking or waking up
  if (backendStatus === 'checking' || backendStatus === 'waking-up') {
    return <ColdStartLoader />;
  }

  // Render app (including blocking error overlay if unreachable)
  return <>{children}</>;
}
