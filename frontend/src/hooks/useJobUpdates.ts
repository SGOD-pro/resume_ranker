import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

const WS_BASE = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';

export function useJobUpdates(jobId: string | null) {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const ws = new WebSocket(`${WS_BASE}/ws/jobs/${jobId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { event: eventType, data } = payload;
        
        // Update TanStack query cache for 'candidates'
        queryClient.setQueryData(['candidates', jobId], (oldData: { candidates: Record<string, unknown>[] } | undefined) => {
          if (!oldData) return oldData;
          
          const candidates = [...oldData.candidates];
          
          if (eventType === 'candidate_partial') {
            const index = candidates.findIndex(c => c.id === data.id);
            if (index > -1) {
              candidates[index] = { ...candidates[index], ...data, status: 'processing' };
            } else {
              candidates.push({ ...data, status: 'processing' });
            }
          } else if (eventType === 'candidate_ready') {
            const index = candidates.findIndex(c => c.id === data.id);
            if (index > -1) {
              candidates[index] = { ...data, status: 'completed' };
            } else {
              candidates.push({ ...data, status: 'completed' });
            }
          }
          
          return {
            ...oldData,
            candidates
          };
        });

      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    return () => {
      ws.close();
    };
  }, [jobId, queryClient]);
}
