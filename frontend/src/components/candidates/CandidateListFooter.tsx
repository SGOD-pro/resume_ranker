import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useCandidateStore } from '@/store/candidate-store';
import { toast } from 'sonner';

export function CandidateListFooter() {
  const { showKnockouts, toggleShowKnockouts, candidates } = useCandidateStore();

  const handleExportCsv = () => {
    if (!candidates || candidates.length === 0) {
      toast.error('No candidates to export.');
      return;
    }

    const headers = [
      'Rank',
      'Name',
      'Email',
      'Phone',
      'Match Score',
      'Signal',
      'Status',
      'Note',
      'Matched Skills',
      'Missing Skills',
      'Experience (Years)',
      'Knocked Out',
      'Knockout Reasons',
    ];

    const rows = candidates.map((c, idx) => [
      c.rank ?? idx + 1,
      `"${(c.name || '').replace(/"/g, '""')}"`,
      `"${(c.email || '').replace(/"/g, '""')}"`,
      `"${(c.phone || '').replace(/"/g, '""')}"`,
      c.overallScore.toFixed(1),
      c.signal,
      c.status,
      `"${(c.note || '').replace(/"/g, '""')}"`,
      `"${(c.skillMatch?.matched || []).join(', ').replace(/"/g, '""')}"`,
      `"${(c.skillMatch?.missing || []).join(', ').replace(/"/g, '""')}"`,
      c.totalYears.toFixed(1),
      c.knockoutChecks?.some((k) => !k.passed) ? 'YES' : 'NO',
      `"${(c.knockoutChecks?.filter((k) => !k.passed).map((k) => k.label) || []).join('; ').replace(/"/g, '""')}"`,
    ]);

    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute(
      'download',
      `sortlist_candidates_${new Date().toISOString().slice(0, 10)}.csv`,
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(`Exported ${candidates.length} candidate(s) to CSV.`);
  };

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
        onClick={handleExportCsv}
        className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-8 hover:bg-foreground hover:text-background transition-colors"
      >
        Export CSV
      </Button>
    </div>
  );
}

