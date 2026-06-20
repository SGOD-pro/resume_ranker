/**
 * UploadProgressBar.tsx — Top-of-page upload progress
 * =====================================================
 * Sits between AppHeader and the 3-panel layout.
 * Only visible during appPhase === 'uploading'.
 * NOT a toast, NOT a modal — the candidate list remains scrollable.
 */

import { Progress } from '@/components/ui/progress';
import { useAppStore } from '@/store/app-store';

export function UploadProgressBar() {
  const appPhase = useAppStore((s) => s.appPhase);
  const uploadProgress = useAppStore((s) => s.uploadProgress);

  if (appPhase !== 'uploading') return null;

  return (
    <div className="w-full bg-secondary border-b border-border px-sp-4 py-sp-1">
      <div className="flex items-center gap-sp-3">
        <span className="text-tiny font-mono font-bold uppercase tracking-chip text-foreground whitespace-nowrap">
          Uploading {uploadProgress.filesUploaded} of {uploadProgress.filesTotal}
        </span>
        <Progress
          value={uploadProgress.percent}
          className="flex-1 h-2 bg-surface-sunken border-2 border-border [&_[data-slot=progress-indicator]]:bg-foreground"
        />
        <span className="text-tiny font-mono font-bold text-foreground w-10 text-right">
          {uploadProgress.percent}%
        </span>
      </div>
      {uploadProgress.currentFile && (
        <p className="text-tiny font-mono text-muted-foreground mt-sp-1 truncate">
          {uploadProgress.currentFile}
        </p>
      )}
    </div>
  );
}
