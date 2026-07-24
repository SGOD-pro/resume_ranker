import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { useWeightsStore } from '@/store/weights-store';

type WeightKey = 'skills' | 'experience' | 'education' | 'semantic';

const weightLabels: { key: WeightKey; label: string }[] = [
  { key: 'skills', label: 'Skills' },
  { key: 'experience', label: 'Experience' },
  { key: 'education', label: 'Education' },
  { key: 'semantic', label: 'Semantic' },
];

export function WeightsSection() {
  const { weights, setWeight } = useWeightsStore();

  const getBarWidth = (value: number): string => {
    if (value >= 80) return 'w-full';
    if (value >= 60) return 'w-4/5';
    if (value >= 40) return 'w-3/5';
    if (value >= 20) return 'w-2/5';
    if (value >= 10) return 'w-1/5';
    return 'w-[5%]';
  };

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0);

  return (
    <div>
      <div className="flex justify-between items-center mb-sp-3">
        <Label className="font-heading text-sm uppercase tracking-chip block text-foreground">
          Weights
        </Label>
        {totalWeight !== 100 && (
          <span className="text-[10px] uppercase font-bold text-red-500">
            Total: {totalWeight}% (Should be 100%)
          </span>
        )}
      </div>
      <div className="space-y-sp-3">
        {weightLabels.map(({ key, label }) => (
          <div key={key}>
            <div className="flex items-center justify-between mb-sp-1">
              <span className="text-tiny uppercase tracking-chip font-semibold text-muted-foreground">
                {label}
              </span>
              <span className="font-mono text-tiny font-bold text-foreground">
                {weights[key]}%
              </span>
            </div>
            <div className="relative mb-sp-1">
              <div className="h-3 w-full bg-surface-sunken border-2 border-border">
                <div
                  className={`h-full bg-foreground transition-all ${getBarWidth(weights[key])}`}
                />
              </div>
            </div>
            <Slider
              value={[weights[key]]}
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
