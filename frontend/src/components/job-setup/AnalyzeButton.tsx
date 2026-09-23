/**
 * AnalyzeButton.tsx — Phase-aware analyze trigger
 * ==================================================
 * - During 'extracting': disabled, tooltip "Extraction in progress"
 * - During 'scoring': disabled, tooltip "Scoring in progress"
 * - On click: validates weights, calls scoring API
 * - On scoring 500/validation error: blocking Alert (not toast)
 */

import { useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useJobStore } from '@/store/job-store';
import { useAppStore } from '@/store/app-store';
import { useCandidateStore } from '@/store/candidate-store';
import { requestAnalysis, getAnalysisStatus, getResults, updateJob, scoreJob } from '@/lib/api';
import { mapScoredCandidates } from '@/lib/mapScoredCandidate';

export function AnalyzeButton() {
  const { isAnalyzing, setAnalyzing, job } = useJobStore();
  const appPhase = useAppStore((s) => s.appPhase);
  const setAppPhase = useAppStore((s) => s.setAppPhase);
  const jobId = useAppStore((s) => s.jobId);
  const setBlockingError = useAppStore((s) => s.setBlockingError);
  const setCandidates = useCandidateStore((s) => s.setCandidates);
  const setUpload = useCandidateStore((s) => s.setUpload);
  const handleClickRef = useRef<(() => Promise<void>) | null>(null);
  // Track whether user clicked Analyze while fast_preprocessing is still running
  const analyzeRequestedRef = useRef(false);


  const isDisabled =
    isAnalyzing ||
    appPhase === 'uploading' ||
    appPhase === 'analysis_queued' ||
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
      case 'analysis_queued':
        return 'Analysis queued';
      case 'fast_preprocessing':
        return 'Click to analyze — parsing continues in background';
      case 'fallback_processing':
        return 'Deeper extraction in progress';
      case 'final_ranking':
      case 'scoring':
        return 'Scoring in progress';
      default:
        return null;
    }
  };

  /** Poll durable upload session progress until terminal state */
  const pollAnalysisProgress = useCallback(
    async (currentJobId: string): Promise<void> => {
      const maxAttempts = 180;
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          const statusRes = await getAnalysisStatus(currentJobId);
          const st = statusRes.status;

          if (st === 'FAST_PREPROCESSING' || st === 'FAST_PARSING') {
            setAppPhase('fast_preprocessing');
          } else if (st === 'ANALYSIS_REQUESTED') {
            setAppPhase('analysis_queued');
          } else if (st === 'FALLBACK_PROCESSING') {
            setAppPhase('fallback_processing');
          } else if (st === 'FINAL_RANKING') {
            setAppPhase('final_ranking');
          } else if (st === 'READY_TO_ANALYZE') {
            // Fast-parse complete, waiting for Analyze click — transition UI
            setAppPhase('ready_to_analyze');
            // If user had already clicked Analyze (race), re-trigger immediately
            if (analyzeRequestedRef.current) {
              handleClickRef.current?.();
            }
            return;
          } else if (st === 'READY' || st === 'READY_WITH_WARNINGS') {
            const results = await getResults(currentJobId);
            const mapped = mapScoredCandidates(results.candidates, currentJobId);
            setCandidates(mapped);
            setUpload({
              totalFiles: results.total_candidates,
              analyzedFiles: results.total_candidates,
              processingFiles: 0,
            });
            setAppPhase('complete');
            toast.success('Analysis complete');
            return;
          } else if (st === 'FAILED') {
            const errDoc = statusRes.documents?.find((d) => d.error_reason);
            throw new Error(errDoc?.error_reason || 'Analysis processing failed.');
          }
        } catch (pollErr: unknown) {
          // If status route not ready or error, continue polling unless terminal
          if (i > 5 && pollErr instanceof Error && pollErr.message.includes('failed')) {
            throw pollErr;
          }
        }
      }
      throw new Error('Analysis timed out. Please refresh to check results.');
    },
    [setAppPhase, setCandidates, setUpload],
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
    // Mark intent in case we're still in fast_preprocessing
    analyzeRequestedRef.current = true;

    try {
      // Phase 0: Push current JD form state to backend
      try {
        await updateJob(jobId, {
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
        });
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'Failed to update job configuration.';
        setBlockingError({
          title: 'Config Update Failed',
          message,
          onRetry: () => handleClickRef.current?.(),
        });
        setAppPhase('ready_to_analyze');
        setAnalyzing(false);
        analyzeRequestedRef.current = false;
        return;
      }

      // Phase 1: Request analysis authorization.
      // If we're still in fast_preprocessing, the backend will persist analysis_requested=True
      // and the coordinator will dispatch ODL/final-rank as soon as fast-parse completes.
      setAppPhase('analysis_queued');
      try {
        await requestAnalysis(jobId, { weights: job.weights });
      } catch (reqErr) {
        console.warn('Direct analysis trigger failed, falling back to synchronous score:', reqErr);
        // Fallback to synchronous score endpoint if legacy backend
        const response = await scoreJob(jobId, { weights: job.weights });
        const mapped = mapScoredCandidates(response.candidates, jobId);
        setCandidates(mapped);
        setUpload({
          totalFiles: response.total_candidates,
          analyzedFiles: response.total_candidates,
          processingFiles: 0,
        });
        setAppPhase('complete');
        toast.success('Analysis complete');
        analyzeRequestedRef.current = false;
        return;
      }

      // Phase 2: Poll durable pipeline progress through barrier and ranking
      await pollAnalysisProgress(jobId);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'An unexpected error occurred during analysis.';
      setBlockingError({
        title: 'Analysis Failed',
        message,
        onRetry: () => handleClickRef.current?.(),
      });
      setAppPhase('ready_to_analyze');
    } finally {
      setAnalyzing(false);
      analyzeRequestedRef.current = false;
    }
  }, [jobId, job, setAnalyzing, setAppPhase, setBlockingError, pollAnalysisProgress, setCandidates, setUpload]);


  useEffect(() => {
    handleClickRef.current = handleClick;
  }, [handleClick]);

  // Background polling: while in fast_preprocessing, poll every 3s to detect
  // when READY_TO_ANALYZE is reached and auto-transition the UI.
  useEffect(() => {
    if (appPhase !== 'fast_preprocessing' || !jobId || isAnalyzing) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const statusRes = await getAnalysisStatus(jobId);
        const st = statusRes.status;
        if (cancelled) return;

        if (st === 'READY_TO_ANALYZE') {
          setAppPhase('ready_to_analyze');
          if (analyzeRequestedRef.current) {
            handleClickRef.current?.();
          }
        } else if (st === 'READY' || st === 'READY_WITH_WARNINGS') {
          // Analysis already completed (e.g. after page refresh)
          setAppPhase('complete');
        } else if (st === 'FAILED') {
          setAppPhase('error');
        }
        // If still FAST_PREPROCESSING, the interval will poll again
      } catch {
        // ignore transient errors — keep polling
      }
    };

    const intervalId = setInterval(poll, 3000);
    poll(); // immediate first check
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [appPhase, jobId, isAnalyzing, setAppPhase]);

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
          {appPhase === 'analysis_queued'
            ? 'Analysis queued…'
            : appPhase === 'fast_preprocessing'
              ? 'Preprocessing…'
              : appPhase === 'fallback_processing'
                ? 'Deep parsing…'
                : appPhase === 'final_ranking' || appPhase === 'scoring'
                  ? 'Scoring…'
                  : 'Analyzing…'}
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
