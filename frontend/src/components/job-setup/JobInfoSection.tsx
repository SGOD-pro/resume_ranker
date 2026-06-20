import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useJobStore } from '@/store/job-store';

export function JobInfoSection() {
  const { job, setTitle, setDepartment } = useJobStore();

  return (
    <div className="space-y-sp-3">
      <div>
        <Label
          htmlFor="job-title"
          className="font-heading text-sm uppercase tracking-chip mb-sp-1 block text-foreground"
        >
          Job Title
        </Label>
        <Input
          id="job-title"
          value={job.title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Senior Backend Eng."
          className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-2.5 h-11 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
        />
      </div>
      <div>
        <Label
          htmlFor="department"
          className="font-heading text-sm uppercase tracking-chip mb-sp-1 block text-foreground"
        >
          Department
        </Label>
        <Input
          id="department"
          value={job.department}
          onChange={(e) => setDepartment(e.target.value)}
          placeholder="Engineering"
          className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-2.5 h-11 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
        />
      </div>
    </div>
  );
}
