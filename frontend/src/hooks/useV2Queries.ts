import { useQuery, useMutation } from '@tanstack/react-query';
import { getCandidatesV2, getCandidateDetailV2, runAtsCheck } from '@/lib/api-v2';

export function useJobCandidates(jobId: string | null) {
  return useQuery({
    queryKey: ['candidates', jobId],
    queryFn: () => getCandidatesV2(jobId!),
    enabled: !!jobId,
  });
}

export function useCandidateDetail(jobId: string | null, candidateId: string | null) {
  return useQuery({
    queryKey: ['candidate', jobId, candidateId],
    queryFn: () => getCandidateDetailV2(jobId!, candidateId!),
    enabled: !!jobId && !!candidateId,
  });
}

export function useAtsCheck() {
  return useMutation({
    mutationFn: runAtsCheck,
  });
}
