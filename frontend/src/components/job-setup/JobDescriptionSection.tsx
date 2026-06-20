import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useJobStore } from '@/store/job-store';

export function JobDescriptionSection() {
  const { job, setDescription } = useJobStore();

  return (
    <div>
      <Label className="font-heading text-sm uppercase tracking-chip mb-sp-1 block text-foreground">
        Job Description
      </Label>
      <Textarea
        value={job.description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Paste JD here..."
        rows={6}
        className="border-thick border-border bg-surface-sunken font-mono text-mono-base p-3 resize-y text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
      />
      <div className="mt-sp-2">
        <Button
          variant="outline"
          className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-small font-semibold px-sp-3 py-sp-1 h-8 hover:bg-foreground hover:text-background transition-colors"
        >
          Upload JD PDF
        </Button>
      </div>
    </div>
  );
}
