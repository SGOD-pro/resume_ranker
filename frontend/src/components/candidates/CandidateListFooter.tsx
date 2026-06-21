import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useCandidateStore } from '@/store/candidate-store';

export function CandidateListFooter() {
  const { showKnockouts, toggleShowKnockouts } = useCandidateStore();

  return (
    <div className="flex items-center justify-between px-sp-4 py-sp-2 bg-background sticky bottom-0">
      <div className="flex items-center gap-sp-2">
        <Switch
          id="show-knockouts"
          checked={showKnockouts}
          onCheckedChange={toggleShowKnockouts}
          className="data-[state=checked]:bg-foreground data-[state=unchecked]:bg-surface-sunken border-thick border-border h-5 w-9 [&_[data-slot=switch-thumb]]:bg-background [&_[data-slot=switch-thumb]]:border-2 [&_[data-slot=switch-thumb]]:border-border [&_[data-slot=switch-thumb]]:size-3.5"
        />
        <Label
          htmlFor="show-knockouts"
          className="text-tiny uppercase tracking-chip font-semibold cursor-pointer text-foreground"
        >
          Show knockouts
        </Label>
      </div>
      <Button
        variant="outline"
        className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-8 hover:bg-foreground hover:text-background transition-colors"
      >
        Export CSV
      </Button>
    </div>
  );
}
