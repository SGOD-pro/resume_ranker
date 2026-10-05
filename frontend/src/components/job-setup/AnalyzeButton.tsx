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
            for (let attempt = 1; attempt <= 15; attempt++) {
              try {
                results = await getResults(currentJobId);
                if (results && Array.isArray(results.candidates) && (results.candidates.length > 0 || totalCandidates === 0)) {
                  break;
                }
              } catch (resErr) {
                if (attempt === 15) throw resErr;
              }
              await new Promise((r) => setTimeout(r, 1000));
            }
            if (!results) throw new Error('No results returned from server');
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
            reject(err);
          }
        };

        const handleFallbackPoll = async () => {
          if (isDone) return;
          try {
            const pollRes = await pollJobStatus(currentJobId, etagRef.current);
            if (pollRes.etag) {
              setEtag(pollRes.etag);
              etagRef.current = pollRes.etag;
            }
            const statusRes = pollRes.status;
            if (statusRes) {
              if (statusRes.files) {
                setJobFiles(statusRes.files);
              }
              const termStatuses = ['DONE', 'DONE_WITH_ERRORS', 'READY', 'READY_WITH_WARNINGS', 'COMPLETED'];
              if (termStatuses.includes(statusRes.status)) {
                await handleSuccess(statusRes.usable_files);
                return;
              }
              if (statusRes.status === 'FAILED') {
                cleanup();
                reject(new Error('Analysis processing failed on server.'));
                return;
              }
            }
          } catch {
            // ignore network glitch on single poll
          }

          if (!isDone) {
            // Adaptive retry: check again in 8s if still processing
            fallbackTimer = setTimeout(handleFallbackPoll, 8000);
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
            // On SSE disconnection, smoothly activate gentle fallback poll without spamming
            if (!isDone && !fallbackTimer) {
              fallbackTimer = setTimeout(handleFallbackPoll, 2000);
            }
          },
        });

        // Safety fallback timer: poll after 8s to guard against silent SSE disconnects
        if (!fallbackTimer) {
          fallbackTimer = setTimeout(handleFallbackPoll, 8000);
        }
      });
    },
    [setAppPhase, setCandidates, setUpload, setEtag, setJobFiles, setIsStalled],
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
        title: 'Analysis Failed',
        message,
        onRetry: () => handleClick(),
      });
      setAppPhase('ready_to_analyze');
    } finally {
      setAnalyzing(false);
    }
  }, [
    jobId,
    job,
    fileIdMap,
    setAnalyzing,
    setAppPhase,
    setBlockingError,
    monitorAnalysisProgress,
  ]);

  const tooltipText = getTooltipText();
  const showTooltip = isDisabled && tooltipText;

  const button = (
    <Button
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
