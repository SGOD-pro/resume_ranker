import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { useCandidateStore } from '@/store/candidate-store';
import type { Candidate, CandidateStatus } from '@/store/types';
import { cn } from '@/lib/utils';

const statusLabels: Record<CandidateStatus, { label: string; classes: string }> = {
  'under-review': { label: 'Under Review', classes: 'border-foreground text-foreground bg-secondary' },
  shortlisted: { label: 'Shortlisted', classes: 'border-success text-success bg-secondary' },
  rejected: { label: 'Rejected', classes: 'border-error text-error bg-secondary' },
  'assessment-sent': { label: 'Assessment Sent', classes: 'border-info text-info bg-secondary' },
};

interface CandidateActionsProps {
  candidate: Candidate;
}

export function CandidateActions({ candidate }: CandidateActionsProps) {
  const { setStatus, setNote } = useCandidateStore();
  const [noteInput, setNoteInput] = useState(candidate.note);
  const [dialogOpen, setDialogOpen] = useState(false);
  const status = statusLabels[candidate.status];

  const handleSaveNote = () => {
    setNote(candidate.id, noteInput);
    setDialogOpen(false);
  };

  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Actions
      </h4>

      <div className="flex flex-wrap gap-sp-2 mb-sp-3">
        <Button
          onClick={() => setStatus(candidate.id, 'shortlisted')}
          className="border-thick border-foreground bg-foreground text-background uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-background hover:text-foreground transition-colors text-background"
        >
          ✓ Shortlist
        </Button>

        <Button
          onClick={() => setStatus(candidate.id, 'rejected')}
          className="border-thick border-error bg-error text-background uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-background hover:text-error transition-colors"
        >
          ✗ Reject
        </Button>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button
              variant="outline"
              className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-foreground hover:text-background transition-colors"
            >
              📝 Note
            </Button>
          </DialogTrigger>
          <DialogContent className="border-heavy border-border bg-card p-sp-4 max-w-md text-foreground">
            <DialogHeader>
              <DialogTitle className="font-heading text-lg uppercase tracking-brutal text-foreground">
                Add Note — {candidate.name}
              </DialogTitle>
            </DialogHeader>
            <Textarea
              value={noteInput}
              onChange={(e) => setNoteInput(e.target.value)}
              placeholder="Internal HR note..."
              rows={4}
              className="border-thick border-border bg-surface-sunken font-mono text-mono-base p-3 mt-sp-2 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
            />
            <div className="flex justify-end gap-sp-2 mt-sp-3">
              <Button
                variant="outline"
                onClick={() => setDialogOpen(false)}
                className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-foreground hover:text-background transition-colors"
              >
                Cancel
              </Button>
              <Button
                onClick={handleSaveNote}
                className="border-thick border-foreground bg-foreground text-background uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-background hover:text-foreground transition-colors"
              >
                Save
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <Button
          onClick={() => setStatus(candidate.id, 'assessment-sent')}
          variant="outline"
          className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-foreground hover:text-background transition-colors"
        >
          📧 Send Assessment
        </Button>
      </div>

      <div className="flex items-center gap-sp-2">
        <span className="text-tiny uppercase tracking-chip font-bold text-muted-foreground">Status:</span>
        <Badge
          className={cn(
            'border-2 px-3 py-0.5 text-[11px] uppercase tracking-chip font-bold',
            status.classes
          )}
        >
          {status.label}
        </Badge>
      </div>

      {candidate.note && (
        <div className="mt-sp-3 border-2 border-muted-foreground p-sp-2">
          <p className="text-tiny uppercase tracking-chip font-bold mb-sp-1 text-muted-foreground">Note:</p>
          <p className="text-small font-mono text-muted-foreground">{candidate.note}</p>
        </div>
      )}
    </div>
  );
}
