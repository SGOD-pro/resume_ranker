import { useQuery, useMutation } from '@tanstack/react-query';
import { getCandidates, getCandidateDetail, runAtsCheck } from '@/lib/api';

export function useJobCandidates(jobId: string | null) {
  return useQuery({
    queryKey: ['candidates', jobId],
    queryFn: () => getCandidates(jobId!),
    enabled: !!jobId,
  });
}

export function useCandidateDetail(jobId: string | null, candidateId: string | null) {
  return useQuery({
    queryKey: ['candidate', jobId, candidateId],
    queryFn: () => getCandidateDetail(jobId!, candidateId!),
    enabled: !!jobId && !!candidateId,
  });
}

export function useAtsCheck() {
  return useMutation({
    mutationFn: runAtsCheck,
  });
}
