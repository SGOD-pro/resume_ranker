/**
 * ResumeUploadZone.tsx — Drag-drop with client-side validation
 * ==============================================================
 * - Rejects non-PDF files instantly via destructive toast
 * - Rejects >10MB files via destructive toast
 * - Never attempts upload for invalid files
 * - If server rejects a file that passed client validation,
 *   toasts it individually without blocking the batch
 */

import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useCandidateStore } from '@/store/candidate-store';
import { useAppStore } from '@/store/app-store';
import { useJobStore } from '@/store/job-store';
import { uploadResumes, createJob } from '@/lib/api';
import type { UploadResult } from '@/lib/api';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

export function ResumeUploadZone() {
  const upload = useCandidateStore((s) => s.upload);
  const setUpload = useCandidateStore((s) => s.setUpload);
  const appPhase = useAppStore((s) => s.appPhase);
  const setAppPhase = useAppStore((s) => s.setAppPhase);
  const setUploadProgress = useAppStore((s) => s.setUploadProgress);
  const resetUploadProgress = useAppStore((s) => s.resetUploadProgress);
  const jobId = useAppStore((s) => s.jobId);
  const setJobId = useAppStore((s) => s.setJobId);
  const job = useJobStore((s) => s.job);

  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** Client-side validation — returns only valid PDF files */
  const validateFiles = useCallback((fileList: FileList | File[]): File[] => {
    const files = Array.from(fileList);
    const valid: File[] = [];

    for (const file of files) {
      // Check extension
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        toast.error(`Rejected: ${file.name}`, {
          description: 'Only PDF files are accepted.',
        });
        continue;
      }

      // Check size
      if (file.size > MAX_FILE_SIZE) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
        toast.error(`Rejected: ${file.name}`, {
          description: `File too large (${sizeMb}MB). Maximum is 10MB.`,
        });
        continue;
      }

      valid.push(file);
    }

    return valid;
  }, []);

  /** Upload valid files to the backend */
  const handleUpload = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;

      setAppPhase('uploading');
      setUploadProgress({
        filesTotal: files.length,
        filesUploaded: 0,
        percent: 0,
        currentFile: files[0].name,
      });

      try {
        // Ensure we have a job ID
        let currentJobId = jobId;
        if (!currentJobId) {
          const jobRes = await createJob({
            title: job.title || 'Untitled Job',
          });
          currentJobId = jobRes.id;
          setJobId(currentJobId);
          toast.success('Job created');
        }

        // Upload with progress tracking
        const result: UploadResult = await uploadResumes(
          currentJobId,
          files,
          (loaded, total) => {
            const percent = Math.round((loaded / total) * 100);
            setUploadProgress({ loaded, total, percent });
          },
        );

        // Toast server-side rejections individually
        for (const rejected of result.rejected) {
          toast.error(`Server rejected: ${rejected.filename}`, {
            description: rejected.reason,
          });
        }

        // Update candidate store with accepted count
        setUpload({
          totalFiles: result.total_accepted,
          analyzedFiles: 0,
          processingFiles: result.accepted.length,
          isUploading: false,
        });

        if (result.accepted.length > 0) {
          toast.success(
            `${result.accepted.length} resume${result.accepted.length > 1 ? 's' : ''} uploaded`,
          );
        }
      } catch (err) {
        toast.error('Upload failed', {
          description: err instanceof Error ? err.message : 'An unexpected error occurred',
        });
      } finally {
        setAppPhase('idle');
        resetUploadProgress();
      }
    },
    [jobId, setJobId, setAppPhase, setUploadProgress, resetUploadProgress, setUpload, job.title],
  );

  // ── Drag-drop handlers ──────────────────────────────────────────────────

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      const validFiles = validateFiles(e.dataTransfer.files);
      handleUpload(validFiles);
    },
    [validateFiles, handleUpload],
  );

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        const validFiles = validateFiles(e.target.files);
        handleUpload(validFiles);
        // Reset input so same files can be re-selected
        e.target.value = '';
      }
    },
    [validateFiles, handleUpload],
  );

  const isDisabled = appPhase === 'uploading' || appPhase === 'extracting' || appPhase === 'scoring';

  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-2 text-foreground">
        Upload Resumes
      </h4>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        multiple
        className="hidden"
        onChange={handleFileInputChange}
        disabled={isDisabled}
      />

      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-thick border-dashed p-sp-4 flex flex-col items-center justify-center gap-sp-2 transition-colors cursor-pointer ${
          isDisabled
            ? 'border-border bg-surface-sunken opacity-50 cursor-not-allowed'
            : isDragging
              ? 'border-foreground bg-surface-hover'
              : 'border-border bg-surface-sunken hover:bg-surface-hover'
        }`}
      >
        <p className="text-small font-semibold uppercase tracking-chip text-center text-muted-foreground">
          {isDragging ? 'Drop PDFs here' : 'Drop PDFs here or click browse'}
        </p>
        <Button
          variant="outline"
          onClick={handleBrowseClick}
          disabled={isDisabled}
          className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 py-sp-1 h-8 hover:bg-foreground hover:text-background transition-colors"
        >
          Browse Files
        </Button>
      </div>

      <div className="mt-sp-2 space-y-sp-1">
        <p className="text-tiny font-mono text-muted-foreground">
          <span className="font-bold text-foreground">{upload.totalFiles}</span> resumes uploaded ·{' '}
          <span className="font-bold text-foreground">{upload.analyzedFiles}</span> analyzed ✓
        </p>
        {upload.processingFiles > 0 && (
          <p className="text-tiny font-mono text-muted-foreground">
            {upload.processingFiles} processing...
          </p>
        )}
      </div>
    </div>
  );
}
