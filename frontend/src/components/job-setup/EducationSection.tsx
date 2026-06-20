import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useJobStore } from '@/store/job-store';
import type { EducationLevel } from '@/store/types';

const educationOptions: { value: EducationLevel; label: string }[] = [
  { value: 'any', label: 'Any' },
  { value: 'high-school', label: 'High School' },
  { value: 'associate', label: 'Associate' },
  { value: 'bachelor', label: 'Bachelor' },
  { value: 'master', label: 'Master' },
  { value: 'doctorate', label: 'Doctorate' },
];

export function EducationSection() {
  const { job, setEducationLevel, setEducationField } = useJobStore();

  return (
    <div>
      <Label className="font-heading text-sm uppercase tracking-chip mb-sp-2 block text-foreground">
        Education
      </Label>
      <div className="space-y-sp-2">
        <div>
          <label className="text-tiny uppercase tracking-chip font-semibold block mb-sp-1 text-muted-foreground">
            Required
          </label>
          <Select
            value={job.educationLevel}
            onValueChange={(val) => setEducationLevel(val as EducationLevel)}
          >
            <SelectTrigger className="border-thick border-border bg-surface-sunken font-mono text-mono-base h-10 px-3 text-foreground focus:border-heavy focus:border-foreground focus:outline-none">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-thick border-border bg-card text-foreground">
              {educationOptions.map((opt) => (
                <SelectItem
                  key={opt.value}
                  value={opt.value}
                  className="font-mono text-mono-base hover:bg-foreground hover:text-background cursor-pointer"
                >
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-tiny uppercase tracking-chip font-semibold block mb-sp-1 text-muted-foreground">
            Field
          </label>
          <Input
            value={job.educationField}
            onChange={(e) => setEducationField(e.target.value)}
            placeholder="CS / related"
            className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-1 h-10 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
          />
        </div>
      </div>
    </div>
  );
}
