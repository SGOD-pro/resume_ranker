import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useCandidateStore } from '@/store/candidate-store';

export function ResumeUploadZone() {
  const upload = useCandidateStore((s) => s.upload);
  const progressPercent =
    upload.totalFiles > 0
      ? Math.round((upload.analyzedFiles / upload.totalFiles) * 100)
      : 0;

  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-2 text-foreground">
        Upload Resumes
      </h4>

      <div className="border-thick border-dashed border-border p-sp-4 flex flex-col items-center justify-center gap-sp-2 bg-surface-sunken hover:bg-surface-hover transition-colors cursor-pointer">
        <p className="text-small font-semibold uppercase tracking-chip text-center text-muted-foreground">
          Drop PDFs here or click browse
        </p>
        <Button
          variant="outline"
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
          <div className="flex items-center gap-sp-2">
            <span className="text-tiny font-mono text-muted-foreground">
              {upload.processingFiles} processing...
            </span>
            <Progress
              value={progressPercent}
              className="flex-1 h-2 bg-surface-sunken border-2 border-border [&_[data-slot=progress-indicator]]:bg-foreground"
            />
            <span className="text-tiny font-mono font-bold text-foreground">{progressPercent}%</span>
          </div>
        )}
      </div>
    </div>
  );
}
