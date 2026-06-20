import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useJobStore } from '@/store/job-store';

export function AnalyzeButton() {
  const { isAnalyzing, setAnalyzing } = useJobStore();

  const handleClick = () => {
    setAnalyzing(true);
    setTimeout(() => setAnalyzing(false), 2000);
  };

  return (
    <Button
      onClick={handleClick}
      disabled={isAnalyzing}
      className="w-full h-12 bg-foreground text-background border-thick border-foreground uppercase tracking-brutal text-sm font-bold hover:bg-background hover:text-foreground transition-colors active:border-heavy disabled:bg-disabled-bg disabled:text-muted-foreground disabled:border-disabled-border disabled:cursor-not-allowed"
    >
      {isAnalyzing ? (
        <span className="flex items-center gap-sp-2">
          <Spinner className="text-current" />
          Analyzing...
        </span>
      ) : (
        'Analyze Resumes'
      )}
    </Button>
  );
}
