import { useEffect, useRef } from 'react';
import { ThreePanelLayout } from '@/components/layout/ThreePanelLayout';
import { UploadProgressBar } from '@/components/layout/UploadProgressBar';
import { useAppStore } from '@/store/app-store';
import { useCandidateStore } from '@/store/candidate-store';
import { useJobStore } from '@/store/job-store';
import { getJobStatus, getResults } from '@/lib/api';
import { mapScoredCandidates } from '@/lib/mapScoredCandidate';
import type { EducationLevel } from '@/store/types';

export function DashboardPage() {
  const jobId = useAppStore((s) => s.jobId);
  const appPhase = useAppStore((s) => s.appPhase);
  const setJobId = useAppStore((s) => s.setJobId);
  const setAppPhase = useAppStore((s) => s.setAppPhase);
  const setJobFiles = useAppStore((s) => s.setJobFiles);
  const setIsStalled = useAppStore((s) => s.setIsStalled);
  const setCandidates = useCandidateStore((s) => s.setCandidates);
  const candidates = useCandidateStore((s) => s.candidates);
  const hasHydratedForJobIdRef = useRef<string | null>(null);

  useEffect(() => {
    // Read stored active_job_id from sessionStorage for page reload state recovery
    const savedJobId =
      jobId || (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('active_job_id') : null);
    if (!savedJobId) return;

    if (hasHydratedForJobIdRef.current === savedJobId) return;

    // Only recover state if candidates are not already loaded in memory
    if (candidates.length > 0 && appPhase === 'complete') return;

    let isSubscribed = true;

    (async () => {
      try {
        const statusRes = await getJobStatus(savedJobId);
        if (!isSubscribed) return;
        if (!statusRes) return;

        if (statusRes.files) {
          setJobFiles(statusRes.files);
        }
        if (statusRes.is_stalled) {
          setIsStalled(true);
        }

        // Restore Job criteria config if provided by backend
        if (statusRes.config && typeof statusRes.config === 'object') {
          const cfg = statusRes.config as Record<string, unknown>;
          useJobStore.setState((state) => ({
            job: {
              ...state.job,
              title: (cfg.title as string) || state.job.title,
              department: (cfg.department as string) ?? state.job.department,
              description: (cfg.description as string) ?? state.job.description,
              mustHaveSkills: (cfg.must_have_skills as string[]) ?? state.job.mustHaveSkills,
              niceToHaveSkills: (cfg.nice_to_have_skills as string[]) ?? state.job.niceToHaveSkills,
              minYears: (cfg.min_years as number) ?? state.job.minYears,
              maxYears: (cfg.max_years as number) ?? state.job.maxYears,
              educationLevel: (cfg.education_level as EducationLevel) ?? state.job.educationLevel,
              educationField: (cfg.education_field as string) ?? state.job.educationField,
              keywords: (cfg.keywords as string[]) ?? state.job.keywords,
              weights: (cfg.weights as typeof state.job.weights) ?? state.job.weights,
            },
          }));
        }

        const termStatuses = ['DONE', 'DONE_WITH_ERRORS', 'READY', 'READY_WITH_WARNINGS', 'COMPLETED'];
        if (termStatuses.includes(statusRes.status)) {
          try {
            const results = await getResults(savedJobId);
            if (!isSubscribed) return;
            if (results && Array.isArray(results.candidates)) {
              const mapped = mapScoredCandidates(results.candidates, savedJobId);
              setCandidates(mapped, savedJobId);
              setAppPhase('complete');
            }
          } catch {
            if (statusRes.usable_files === 0) {
              setCandidates([], savedJobId);
              setAppPhase('complete');
            }
          }
        } else if (
          statusRes.status === 'PROCESSING' ||
          statusRes.status === 'FALLBACK_PROCESSING' ||
          statusRes.status === 'FAST_PREPROCESSING'
        ) {
          setAppPhase('processing');
        } else if (statusRes.status === 'SCORING' || statusRes.status === 'FINAL_RANKING') {
          setAppPhase('scoring');
        } else if (statusRes.status === 'READY_TO_ANALYZE') {
          setAppPhase('ready_to_analyze');
        } else if (statusRes.status === 'FAILED') {
          setAppPhase('error');
        }

        hasHydratedForJobIdRef.current = savedJobId;
        setJobId(savedJobId);
      } catch (err: unknown) {
        console.error('[DASHBOARD HYDRATE ERROR]', err);
        // If job does not exist on backend (404/403), remove stale identifier
        const errStatus =
          err && typeof err === 'object' && 'status' in err
            ? (err as { status: number }).status
            : undefined;
        if (errStatus === 404 || errStatus === 403) {
          setJobId(null);
          try {
            sessionStorage.removeItem('active_job_id');
          } catch (sessionErr) {
            void sessionErr;
          }
        }
      }
    })();

    return () => {
      isSubscribed = false;
    };
  }, [jobId, appPhase, candidates.length, setJobId, setAppPhase, setJobFiles, setIsStalled, setCandidates]);

  return (
    <>
      <UploadProgressBar />
      <ThreePanelLayout />
    </>
  );
}
