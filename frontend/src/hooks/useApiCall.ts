/**
 * useApiCall.ts — Centralized API call hook
 * ============================================
 * Every API call in components MUST go through this hook.
 * Handles loading state, error routing (toast vs Alert vs silent),
 * and retry logic with exponential backoff.
 */

import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import { useAppStore } from '@/store/app-store';

export type ErrorDisplay = 'toast' | 'alert' | 'silent';

export interface UseApiCallOptions {
  /** How to display errors. Defaults to 'toast'. */
  errorDisplay?: ErrorDisplay;
  /** Number of retries before giving up. Defaults to 0. */
  retries?: number;
  /** Base backoff delay in ms. Doubles each retry. Defaults to 1000. */
  retryBackoffMs?: number;
  /** Success callback */
  onSuccess?: (data: unknown) => void;
  /** Error callback (in addition to the display) */
  onError?: (error: Error) => void;
  /** Success toast message. If provided, shows a success toast on completion. */
  successMessage?: string;
}

interface UseApiCallReturn<T> {
  execute: (...args: unknown[]) => Promise<T | undefined>;
  isLoading: boolean;
  error: Error | null;
  reset: () => void;
}

export function useApiCall<T>(
  apiFn: (...args: unknown[]) => Promise<T>,
  options: UseApiCallOptions = {},
): UseApiCallReturn<T> {
  const {
    errorDisplay = 'toast',
    retries = 0,
    retryBackoffMs = 1000,
    onSuccess,
    onError,
    successMessage,
  } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const setBlockingError = useAppStore((s) => s.setBlockingError);

  const execute = useCallback(
    async (...args: unknown[]): Promise<T | undefined> => {
      // Cancel any in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setIsLoading(true);
      setError(null);

      let lastError: Error | null = null;

      for (let attempt = 0; attempt <= retries; attempt++) {
        try {
          const result = await apiFn(...args);
          setIsLoading(false);

          if (successMessage) {
            toast.success(successMessage);
          }
          onSuccess?.(result);
          return result;
        } catch (err) {
          lastError = err instanceof Error ? err : new Error(String(err));

          // Don't retry if aborted
          if (lastError.name === 'AbortError') {
            setIsLoading(false);
            return undefined;
          }

          // Retry with backoff (except on last attempt)
          if (attempt < retries) {
            const delay = retryBackoffMs * Math.pow(2, attempt);
            await new Promise((r) => setTimeout(r, delay));
          }
        }
      }

      // All attempts exhausted
      setIsLoading(false);
      setError(lastError);
      onError?.(lastError!);

      // Route error to the correct UI
      const message =
        lastError instanceof ApiError && lastError.body
          ? typeof lastError.body === 'object' &&
            lastError.body !== null &&
            'detail' in lastError.body
            ? String((lastError.body as { detail: unknown }).detail)
            : JSON.stringify(lastError.body)
          : lastError?.message || 'An unexpected error occurred';

      switch (errorDisplay) {
        case 'toast':
          toast.error(message);
          break;
        case 'alert':
          setBlockingError({
            title: 'Error',
            message,
          });
          break;
        case 'silent':
          // Caller handles it via onError callback
          break;
      }

      return undefined;
    },
    [apiFn, retries, retryBackoffMs, errorDisplay, onSuccess, onError, successMessage, setBlockingError],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    setError(null);
  }, []);

  return { execute, isLoading, error, reset };
}
