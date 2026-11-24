/**
 * AnalyzeButton.tsx — Phase 2 barrier trigger and short-polling status
 * ====================================================================
 * - Submits explicit file_ids and JD criteria via POST /api/v2/jobs/{job_id}/analyze
 * - Polls GET /api/v2/jobs/{job_id}/status using ETag / 304 Not Modified
 * - Updates per-file progress and handles is_stalled detection
 * - Fetches final rankings from GET /api/v2/jobs/{job_id}/results upon terminal DONE
 */

import { useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useJobStore } from '@/store/job-store';
import { useAppStore } from '@/store/app-store';
import { useCandidateStore } from '@/store/candidate-store';
import {
  triggerAnalysis,
  pollJobStatus,
  getJobStatus,
  getResults,
  subscribeToJobExtraction,
} from '@/lib/api';
import { mapScoredCandidates } from '@/lib/mapScoredCandidate';

export function AnalyzeButton() {
  const { isAnalyzing, setAnalyzing, job } = useJobStore();
  const appPhase = useAppStore((s) => s.appPhase);
  const setAppPhase = useAppStore((s) => s.setAppPhase);
  const jobId = useAppStore((s) => s.jobId);
  const fileIdMap = useAppStore((s) => s.fileIdMap);
  const etag = useAppStore((s) => s.etag);
  const setEtag = useAppStore((s) => s.setEtag);
  const setJobFiles = useAppStore((s) => s.setJobFiles);
  const jobFiles = useAppStore((s) => s.jobFiles);
  const setIsStalled = useAppStore((s) => s.setIsStalled);
  const setBlockingError = useAppStore((s) => s.setBlockingError);
  const resetUploadProgress = useAppStore((s) => s.resetUploadProgress);
  const setCandidates = useCandidateStore((s) => s.setCandidates);
  const setUpload = useCandidateStore((s) => s.setUpload);
  const etagRef = useRef<string | null>(etag);

  useEffect(() => {
    etagRef.current = etag;
  }, [etag]);

  const isDisabled =
    isAnalyzing ||
    appPhase === 'uploading' ||
    appPhase === 'analysis_queued' ||
    appPhase === 'processing' ||
    appPhase === 'fallback_processing' ||
    appPhase === 'final_ranking' ||
    appPhase === 'scoring' ||
    !jobId;

  const getTooltipText = () => {
    if (!jobId) {
      return 'Upload resumes first to begin analysis';
    }
    switch (appPhase) {
      case 'uploading':
        return 'Upload in progress';
      case 'processing':
      case 'fallback_processing':
        return 'Analysis and deep extraction in progress';
      case 'scoring':
      case 'final_ranking':
        return 'Scoring in progress';
      default:
        return null;
    }
  };

  const monitorProgressRef = useRef<(id: string) => Promise<void>>(() => Promise.resolve());
  const handleClickRef = useRef<() => Promise<void>>(() => Promise.resolve());

  /** Stream job status via Server-Sent Events (SSE) without continuous hard short-polling */
  const monitorAnalysisProgress = useCallback(
    (currentJobId: string): Promise<void> => {
      return new Promise<void>((resolve, reject) => {
        let isDone = false;
        let unsubscribe: (() => void) | null = null;
        let fallbackTimer: ReturnType<typeof setTimeout> | null = null;

        const cleanup = () => {
          if (unsubscribe) {
            unsubscribe();
            unsubscribe = null;
          }
          if (fallbackTimer) {
            clearTimeout(fallbackTimer);
            fallbackTimer = null;
          }
        };

        const handleSuccess = async (totalCandidates?: number) => {
          if (isDone) return;
          isDone = true;
          cleanup();
          try {
            // Retry getResults up to 15 times with 1s backoff to handle S3 scoring write finalization
            let results: Awaited<ReturnType<typeof getResults>> | null = null;
            let lastError: unknown = null;
            for (let attempt = 1; attempt <= 15; attempt++) {
              try {
                results = await getResults(currentJobId);
                if (
                  results &&
                  Array.isArray(results.candidates) &&
                  (results.candidates.length > 0 || totalCandidates === 0 || results.total_candidates === 0)
                ) {
                  break;
                }
              } catch (resErr: unknown) {
                lastError = resErr;
                const errStatus =
                  resErr && typeof resErr === 'object' && 'status' in resErr
                    ? (resErr as { status: number }).status
                    : undefined;
                // If 409 Conflict, backend results are still being finalized -> wait and retry
                if (errStatus === 409) {
                  await new Promise((r) => setTimeout(r, 1000));
                  continue;
                }
                if (attempt === 15) throw resErr;
              }
              await new Promise((r) => setTimeout(r, 1000));
            }
            if (!results) {
              throw lastError instanceof Error
                ? lastError
                : new Error('No results returned from server after scoring completion.');
            }
            const mapped = mapScoredCandidates(results.candidates || [], currentJobId);
            setCandidates(mapped);
            setUpload({
              totalFiles: totalCandidates ?? results.total_candidates ?? mapped.length,
              analyzedFiles: results.total_candidates ?? mapped.length,
              processingFiles: 0,
            });
            setAppPhase('complete');
            toast.success('Analysis complete');
            resolve();
          } catch (err) {
            setAppPhase('ready_to_analyze');
            setBlockingError({
              title: 'Results Unavailable',
              message:
                err instanceof Error
                  ? err.message
                  : 'Scoring completed but results could not be retrieved from storage.',
              onRetry: () => handleSuccess(totalCandidates),
            });
            reject(err);
          }
        };

        let consecutivePollErrors = 0;
        const handleFallbackPoll = async () => {
          if (isDone) return;
          try {
            const pollRes = await pollJobStatus(currentJobId, etagRef.current);
            consecutivePollErrors = 0;
            if (pollRes.etag) {
              setEtag(pollRes.etag);
              etagRef.current = pollRes.etag;
            }
            const statusRes = pollRes.status;
            if (statusRes) {
              if (statusRes.files) {
                setJobFiles(statusRes.files);
              }
              if (statusRes.is_stalled) {
                setIsStalled(true);
              }
              const termStatuses = ['DONE', 'DONE_WITH_ERRORS', 'READY', 'READY_WITH_WARNINGS', 'COMPLETED'];
              if (termStatuses.includes(statusRes.status)) {
                await handleSuccess(statusRes.usable_files);
                return;
              }
              if (statusRes.status === 'FAILED') {
                cleanup();
                setAppPhase('error');
                reject(new Error('Analysis processing failed on server.'));
                return;
              }
              if (statusRes.status === 'PROCESSING' || statusRes.status === 'FALLBACK_PROCESSING') {
                setAppPhase('processing');
              } else if (statusRes.status === 'SCORING' || statusRes.status === 'FINAL_RANKING') {
                setAppPhase('scoring');
              }
            }
          } catch {
            consecutivePollErrors++;
            if (consecutivePollErrors >= 5) {
              cleanup();
              // Maintain active state rather than erroneously reverting authoritative state
              setBlockingError({
                title: 'Connection Lost',
                message:
                  'Unable to reach backend status after multiple attempts. Analysis continues in the background on the server.',
                onRetry: async () => {
                  setBlockingError(null);
                  try {
                    const statusRes = await getJobStatus(currentJobId);
                    const termStatuses = ['DONE', 'DONE_WITH_ERRORS', 'READY', 'READY_WITH_WARNINGS', 'COMPLETED'];
                    if (termStatuses.includes(statusRes.status)) {
                      await handleSuccess(statusRes.usable_files);
                      return;
                    }
                    if (statusRes.status === 'FAILED') {
                      setAppPhase('error');
                      return;
                    }
                    monitorProgressRef.current(currentJobId).catch(() => {});
                  } catch (pollErr) {
                    void pollErr;
                    monitorProgressRef.current(currentJobId).catch(() => {});
                  }
                },
              });
              reject(new Error('Connection lost after repeated polling failures.'));
              return;
            }
          }

          if (!isDone) {
            const pollDelay = consecutivePollErrors > 0 ? 1000 : 3000;
            fallbackTimer = setTimeout(handleFallbackPoll, pollDelay);
          }
        };

        unsubscribe = subscribeToJobExtraction(currentJobId, {
          onProgress: (data) => {
            if (isDone) return;
            if (data.files) {
              setJobFiles(data.files);
            }
            if (data.is_stalled) {
              setIsStalled(true);
            }
            const st = data.job_status || data.status;
            const termStatuses = ['DONE', 'DONE_WITH_ERRORS', 'READY', 'READY_WITH_WARNINGS', 'COMPLETED', 'complete'];
            if ((st && termStatuses.includes(st)) || (data.status && termStatuses.includes(data.status))) {
              handleSuccess(data.usable_files ?? data.total_files);
              return;
            }

            if (st === 'PROCESSING' || st === 'FALLBACK_PROCESSING' || st === 'FAST_PREPROCESSING' || st === 'extracting') {
              setAppPhase('processing');
            } else if (st === 'SCORING' || st === 'FINAL_RANKING' || st === 'scoring') {
              setAppPhase('scoring');
            }
            if (data.total_files !== undefined) {
              setUpload({
                totalFiles: data.total_files,
                analyzedFiles: data.usable_files ?? (data.total_files - (data.remaining ?? 0)),
                processingFiles: data.remaining ?? 0,
              });
            }
          },
          onComplete: async (data) => {
            await handleSuccess(data.usable);
          },
          onError: () => {
            // On SSE disconnection, smoothly activate gentle fallback poll without delay
            if (!isDone && !fallbackTimer) {
              fallbackTimer = setTimeout(handleFallbackPoll, 500);
            }
          },
        });

        // Safety fallback timer: poll after 2s to guard against silent SSE disconnects
        if (!fallbackTimer) {
          fallbackTimer = setTimeout(handleFallbackPoll, 2000);
        }
      });
    },
    [setAppPhase, setCandidates, setUpload, setEtag, setJobFiles, setIsStalled, setBlockingError],
  );

  const handleClick = useCallback(async () => {
    if (!jobId) {
      toast.error('No job created yet. Upload resumes first.');
      return;
    }

    // Client-side weights validation
    const weightsSum = Object.values(job.weights).reduce((a, b) => a + b, 0);
    if (Math.abs(weightsSum - 100) > 0.01) {
      setBlockingError({
        title: 'Invalid Weights',
        message: `Score weights must sum to 100%. Current total: ${weightsSum}%.`,
        onRetry: () => {},
      });
      return;
    }

    setAnalyzing(true);
    resetUploadProgress();
    setAppPhase('processing');

    try {
      // Submit explicit file IDs and finalized criteria directly to analysis barrier
      const resolvedFileIds =
        Object.values(fileIdMap).length > 0
          ? Object.values(fileIdMap)
          : (jobFiles || []).map((f) => f.file_id);

      const analysisPayload: Parameters<typeof triggerAnalysis>[1] = {
        title: job.title || 'Untitled Job',
        department: job.department,
        description: job.description,
        must_have_skills: job.mustHaveSkills,
        nice_to_have_skills: job.niceToHaveSkills,
        min_years: job.minYears,
        max_years: job.maxYears,
        education_level: job.educationLevel,
        education_field: job.educationField,
        keywords: job.keywords,
        weights: job.weights,
      };

      if (resolvedFileIds.length > 0) {
        analysisPayload.file_ids = resolvedFileIds;
      }

      await triggerAnalysis(jobId, analysisPayload);

      // Stream real-time progress via SSE
      await monitorAnalysisProgress(jobId);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'An unexpected error occurred during analysis.';
      setBlockingError({
        title: 'Analysis Interrupted',
        message,
        onRetry: async () => {
          setBlockingError(null);
          if (jobId) {
            try {
              const statusRes = await getJobStatus(jobId);
              const termStatuses = ['DONE', 'DONE_WITH_ERRORS', 'READY', 'READY_WITH_WARNINGS', 'COMPLETED'];
              if (termStatuses.includes(statusRes.status) || statusRes.status === 'PROCESSING' || statusRes.status === 'SCORING' || statusRes.analyze_requested) {
                // Recover and resume existing job without duplicate POST submission
                await monitorProgressRef.current(jobId);
                return;
              }
            } catch (err) {
              void err;
            }
          }
          handleClickRef.current();
        },
      });
    } finally {
      setAnalyzing(false);
    }
  }, [
    jobId,
    job,
    jobFiles,
    fileIdMap,
    resetUploadProgress,
    setAnalyzing,
    setAppPhase,
    setBlockingError,
    monitorAnalysisProgress,
  ]);

  useEffect(() => {
    monitorProgressRef.current = monitorAnalysisProgress;
    handleClickRef.current = handleClick;
  }, [monitorAnalysisProgress, handleClick]);

  // Reattach monitoring on browser reload/navigation when job was already in progress
  useEffect(() => {
    if (jobId && (appPhase === 'processing' || appPhase === 'scoring') && !isAnalyzing) {
      setAnalyzing(true);
      monitorAnalysisProgress(jobId).finally(() => {
        setAnalyzing(false);
      });
    }
  }, [jobId, appPhase, isAnalyzing, setAnalyzing, monitorAnalysisProgress]);

  const tooltipText = getTooltipText();
  const showTooltip = isDisabled && tooltipText;

  const button = (
    <Button
      data-testid="analyze-button"
      onClick={handleClick}
      disabled={isDisabled}
      className="w-full h-12 bg-foreground text-background border-thick border-foreground uppercase tracking-brutal text-sm font-bold hover:bg-background hover:text-foreground transition-colors active:border-heavy disabled:bg-disabled-bg disabled:text-muted-foreground disabled:border-disabled-border disabled:cursor-not-allowed"
    >
      {isAnalyzing ? (
        <span className="flex items-center gap-sp-2">
          <Spinner className="text-current" />
          {appPhase === 'scoring' ? 'Scoring…' : 'Analyzing…'}
        </span>
      ) : (
        'Analyze Resumes'
      )}
    </Button>
  );

  if (showTooltip) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="block w-full">{button}</span>
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return button;
}
