/**
 * AnalyzeButton.tsx — Phase-aware analyze trigger
 * ==================================================
 * - During 'extracting': disabled, tooltip "Extraction in progress"
 * - During 'scoring': disabled, tooltip "Scoring in progress"
 * - On click: validates weights, calls scoring API
 * - On scoring 500/validation error: blocking Alert (not toast)
 */

import { useCallback } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useJobStore } from '@/store/job-store';
import { useAppStore } from '@/store/app-store';
import { useCandidateStore } from '@/store/candidate-store';
import { startExtraction, scoreJob, updateJob } from '@/lib/api';
import { mapScoredCandidates } from '@/lib/mapScoredCandidate';

const MAX_SSE_RETRIES = 3;
const SSE_RETRY_DELAY_MS = 2000;

export function AnalyzeButton() {
  const { isAnalyzing, setAnalyzing, job } = useJobStore();
  const appPhase = useAppStore((s) => s.appPhase);
  const setAppPhase = useAppStore((s) => s.setAppPhase);
  const jobId = useAppStore((s) => s.jobId);
  const setBlockingError = useAppStore((s) => s.setBlockingError);
  const setSseRetryCount = useAppStore((s) => s.setSseRetryCount);
  const setCandidates = useCandidateStore((s) => s.setCandidates);
  const setUpload = useCandidateStore((s) => s.setUpload);

  const isDisabled =
    isAnalyzing ||
    appPhase === 'extracting' ||
    appPhase === 'scoring' ||
    appPhase === 'uploading';

  const getTooltipText = () => {
    switch (appPhase) {
      case 'extracting':
        return 'Extraction in progress';
      case 'scoring':
        return 'Scoring in progress';
      case 'uploading':
        return 'Upload in progress';
      default:
        return null;
    }
  };

  /** Run SSE extraction with auto-retry */
  const runExtraction = useCallback(
    (currentJobId: string): Promise<void> => {
      return new Promise((resolve, reject) => {
        let retryCount = 0;

        const attemptConnect = () => {
          setSseRetryCount(retryCount);

          const cleanup = startExtraction(
            currentJobId,
            // onEvent — no-op; progress UI can be added here in the future
            () => {
              // Could update progress UI here in the future
            },
            // onError
            (error: Error) => {
              retryCount++;
              setSseRetryCount(retryCount);

              if (retryCount <= MAX_SSE_RETRIES) {
                toast.warning(`Connection lost. Reconnecting… (${retryCount}/${MAX_SSE_RETRIES})`);
                setTimeout(attemptConnect, SSE_RETRY_DELAY_MS * retryCount);
              } else {
                setSseRetryCount(0);
                reject(error);
              }
            },
            // onComplete
            () => {
              setSseRetryCount(0);
              resolve();
            },
          );

          // Store cleanup ref (could be used for unmount)
          void cleanup;
        };

        attemptConnect();
      });
    },
    [setSseRetryCount],
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
        onRetry: () => {
          // Just dismiss — user needs to fix weights
        },
      });
      return;
    }

    setAnalyzing(true);

    try {
      // Phase 0: Push current JD form state to backend
      // The job was created at upload time with empty/default config.
      // Now that the user has filled the form, sync it before scoring.
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
          onRetry: () => handleClick(),
        });
        setAppPhase('idle');
        setAnalyzing(false);
        return;
      }

      // Phase 1: Extraction (SSE)
      setAppPhase('extracting');
      try {
        await runExtraction(jobId);
        toast.success('Extraction complete');
      } catch {
        // SSE failed after all retries
        setBlockingError({
          title: 'Extraction Failed',
          message:
            'Lost connection to the server during extraction after multiple reconnection attempts. Please try again.',
          onRetry: () => handleClick(),
        });
        setAppPhase('idle');
        setAnalyzing(false);
        return;
      }

      // Phase 2: Scoring
      setAppPhase('scoring');
      try {
        const response = await scoreJob(jobId, { weights: job.weights });

        // ── STEP 1 DEBUG: Raw backend response before any frontend mapping ──
        // Logs knockout fields exactly as the backend returned them.
        console.group('[SCORE API] Raw backend response');
        console.log('Total candidates:', response.total_candidates);
        response.candidates.forEach((c: Record<string, unknown>, i: number) => {
          console.group(`[${i + 1}] ${c.name ?? 'Unknown'}`);
          console.table({
            knocked_out:       c.knocked_out,
            final_score:       c.final_score,
            matched_must_have: JSON.stringify(c.matched_must_have ?? []),
            missing_must_have: JSON.stringify(c.missing_must_have ?? []),
            knockout_reasons:  JSON.stringify(c.knockout_reasons ?? []),
          });
          console.groupEnd();
        });
        console.groupEnd();

        // ── STEP 5: Use setCandidates (full replacement, never append) ──────
        const mapped = mapScoredCandidates(response.candidates);
        setCandidates(mapped);
        setUpload({
          totalFiles: response.total_candidates,
          analyzedFiles: response.total_candidates,
          processingFiles: 0,
        });
        toast.success('Analysis complete');
        setAppPhase('complete');
      } catch (err) {
        // Scoring error → blocking Alert (not toast)
        const message =
          err instanceof Error ? err.message : 'An unexpected error occurred during scoring.';
        setBlockingError({
          title: 'Scoring Failed',
          message,
          onRetry: () => handleClick(),
        });
        setAppPhase('idle');
      }
    } finally {
      setAnalyzing(false);
    }
  }, [jobId, job, setAnalyzing, setAppPhase, setBlockingError, runExtraction, setCandidates, setUpload]);

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
          {appPhase === 'extracting' ? 'Extracting…' : appPhase === 'scoring' ? 'Scoring…' : 'Analyzing…'}
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
