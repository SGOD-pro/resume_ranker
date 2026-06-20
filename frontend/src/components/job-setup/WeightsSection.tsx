import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { useJobStore } from '@/store/job-store';
import type { Job } from '@/store/types';

const weightLabels: { key: keyof Job['weights']; label: string }[] = [
  { key: 'skills', label: 'Skills' },
  { key: 'experience', label: 'Experience' },
  { key: 'keywords', label: 'Keywords' },
  { key: 'education', label: 'Education' },
];

export function WeightsSection() {
  const { job, setWeight } = useJobStore();

  const getBarWidth = (value: number): string => {
    if (value >= 80) return 'w-full';
    if (value >= 60) return 'w-4/5';
    if (value >= 40) return 'w-3/5';
    if (value >= 20) return 'w-2/5';
    if (value >= 10) return 'w-1/5';
    return 'w-[5%]';
  };

  return (
    <div>
      <Label className="font-heading text-sm uppercase tracking-chip mb-sp-3 block text-foreground">
        Weights
      </Label>
      <div className="space-y-sp-3">
        {weightLabels.map(({ key, label }) => (
          <div key={key}>
            <div className="flex items-center justify-between mb-sp-1">
              <span className="text-tiny uppercase tracking-chip font-semibold text-muted-foreground">
                {label}
              </span>
              <span className="font-mono text-tiny font-bold text-foreground">
                {job.weights[key]}%
              </span>
            </div>
            <div className="relative mb-sp-1">
              <div className="h-3 w-full bg-surface-sunken border-2 border-border">
                <div
                  className={`h-full bg-foreground transition-all ${getBarWidth(job.weights[key])}`}
                />
              </div>
            </div>
            <Slider
              value={[job.weights[key]]}
              onValueChange={([val]) => setWeight(key, val)}
              min={0}
              max={100}
              step={5}
              className="[&_[data-slot=slider-track]]:h-1 [&_[data-slot=slider-track]]:bg-surface-sunken [&_[data-slot=slider-track]]:border-2 [&_[data-slot=slider-track]]:border-border [&_[data-slot=slider-range]]:bg-foreground [&_[data-slot=slider-thumb]]:border-thick [&_[data-slot=slider-thumb]]:border-foreground [&_[data-slot=slider-thumb]]:bg-background [&_[data-slot=slider-thumb]]:w-4 [&_[data-slot=slider-thumb]]:h-4"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
