/**
 * useJobUpdates.ts — no-op stub
 * ================================
 * WebSocket-based live updates are not used in this architecture.
 * Extraction progress is handled via SSE (startExtraction in AnalyzeButton).
 * WebSockets are also incompatible with AWS Lambda deployments.
 *
 * This hook is kept as a stub so any components that import it don't break.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function useJobUpdates(_jobId: string | null): void {
  // No-op: SSE in AnalyzeButton handles all progress updates.
}
