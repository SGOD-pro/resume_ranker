import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useJobStore } from '@/store/job-store';

export function ExperienceSection() {
  const { job, setMinYears, setMaxYears } = useJobStore();

  return (
    <div>
      <Label className="font-heading text-sm uppercase tracking-chip mb-sp-2 block text-foreground">
        Experience
      </Label>
      <div className="flex items-center gap-sp-3">
        <div className="flex-1">
          <label className="text-tiny uppercase tracking-chip font-semibold block mb-sp-1 text-muted-foreground">
            Min years
          </label>
          <Input
            type="number"
            value={job.minYears}
            onChange={(e) => setMinYears(Number(e.target.value))}
            min={0}
            className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-1 h-10 w-full text-center text-foreground focus:border-heavy focus:border-foreground focus:outline-none"
          />
        </div>
        <div className="flex-1">
          <label className="text-tiny uppercase tracking-chip font-semibold block mb-sp-1 text-muted-foreground">
            Max years
          </label>
          <Input
            type="number"
            value={job.maxYears}
            onChange={(e) => setMaxYears(Number(e.target.value))}
            min={0}
            className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-1 h-10 w-full text-center text-foreground focus:border-heavy focus:border-foreground focus:outline-none"
          />
        </div>
      </div>
    </div>
  );
}
