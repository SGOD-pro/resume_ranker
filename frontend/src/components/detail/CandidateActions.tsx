import { useState, useEffect } from 'react';
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
import { useAppStore } from '@/store/app-store';
import { updateCandidateDecision } from '@/lib/api';
import type { Candidate, CandidateStatus } from '@/store/types';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { SendHorizonalIcon, X, Check, NotebookPen, RotateCcw } from 'lucide-react';

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
  const { jobId } = useAppStore();
  const [noteInput, setNoteInput] = useState(candidate.note || '');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const status = statusLabels[candidate.status] || statusLabels['under-review'];

  useEffect(() => {
    setNoteInput(candidate.note || '');
  }, [candidate.id, candidate.note]);

  const handleShortlist = async () => {
    setStatus(candidate.id, 'shortlisted');
    toast.success(`${candidate.name} marked as Shortlisted.`);
    if (jobId) {
      try {
        await updateCandidateDecision(jobId, candidate.id, { decision: 'shortlisted' });
      } catch {
        // Optimistic UI update already applied
      }
    }
  };

  const handleConfirmReject = async () => {
    const trimmed = rejectReason.trim();
    if (!trimmed) {
      toast.error('Rejection requires a documented reason per v2 transparency policy.');
      return;
    }

    setStatus(candidate.id, 'rejected');
    setNote(candidate.id, `Rejection reason: ${trimmed}`);
    setRejectDialogOpen(false);
    setRejectReason('');
    toast.info(`${candidate.name} marked as Rejected.`);

    if (jobId) {
      try {
        await updateCandidateDecision(jobId, candidate.id, {
          decision: 'rejected',
          reason: trimmed,
          note: `Rejection reason: ${trimmed}`,
        });
      } catch {
        // Optimistic UI
      }
    }
  };

  const handleSaveNote = async () => {
    setNote(candidate.id, noteInput);
    setDialogOpen(false);
    toast.success('Note saved.');
    if (jobId) {
      try {
        await updateCandidateDecision(jobId, candidate.id, {
          note: noteInput,
        });
      } catch {
        // Optimistic UI
      }
    }
  };

  const handleSendAssessment = async () => {
    setStatus(candidate.id, 'assessment-sent');
    toast.success(`Assessment invitation sent to ${candidate.name}.`);
    if (jobId) {
      try {
        await updateCandidateDecision(jobId, candidate.id, {
          decision: 'interview',
          note: 'Assessment invitation sent.',
        });
      } catch {
        // Optimistic UI
      }
    }
  };

  const handleResetToReview = async () => {
    setStatus(candidate.id, 'under-review');
    toast.info(`${candidate.name} returned to Under Review.`);
    if (jobId) {
      try {
        await updateCandidateDecision(jobId, candidate.id, { decision: 'reviewing' });
      } catch {
        // Optimistic UI
      }
    }
  };

  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Recruiter Actions
      </h4>

      <div className="flex flex-wrap gap-sp-2 mb-sp-3">
        {/* Shortlist Button */}
        <Button
          onClick={handleShortlist}
          aria-label={`Shortlist ${candidate.name}`}
          className={cn(
            'border-thick border-success uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 transition-colors flex items-center justify-center gap-1.5 grow',
            candidate.status === 'shortlisted'
              ? 'bg-success text-background hover:bg-success/90'
              : 'bg-secondary text-success hover:bg-success hover:text-background'
          )}
        >
          <Check size={16} /> {candidate.status === 'shortlisted' ? 'Shortlisted ✓' : 'Shortlist'}
        </Button>

        {/* Reject Button with Mandatory Reason Dialog */}
        <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
          <DialogTrigger asChild>
            <Button
              aria-label={`Reject ${candidate.name}`}
              className={cn(
                'border-thick border-error uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 transition-colors flex items-center justify-center gap-1.5 grow',
                candidate.status === 'rejected'
                  ? 'bg-error text-background hover:bg-error/90'
                  : 'bg-secondary text-error hover:bg-error hover:text-background'
              )}
            >
              <X size={16} /> {candidate.status === 'rejected' ? 'Rejected ✗' : 'Reject'}
            </Button>
          </DialogTrigger>
          <DialogContent className="border-heavy border-border bg-card p-sp-4 max-w-md text-foreground">
            <DialogHeader>
              <DialogTitle className="font-heading text-lg uppercase tracking-brutal text-foreground">
                Document Rejection Reason
              </DialogTitle>
            </DialogHeader>
            <p className="text-xs text-muted-foreground font-mono mt-1">
              Per non-negotiable review policy, rejections must include an evidence-backed rationale.
            </p>
            <Textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="e.g. Insufficient verified experience with PyTorch; lacks required distributed systems exposure..."
              rows={4}
              className="border-thick border-border bg-surface-sunken font-mono text-mono-base p-3 mt-sp-2 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
            />
            <div className="flex justify-end gap-sp-2 mt-sp-3">
              <Button
                variant="outline"
                onClick={() => setRejectDialogOpen(false)}
                className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-foreground hover:text-background transition-colors"
              >
                Cancel
              </Button>
              <Button
                onClick={handleConfirmReject}
                className="border-thick border-error bg-error text-background uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-background hover:text-error transition-colors"
              >
                Confirm Rejection
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Send Assessment / Interview Button */}
        <Button
          onClick={handleSendAssessment}
          aria-label={`Send assessment to ${candidate.name}`}
          className={cn(
            'border-thick border-info uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 transition-colors flex items-center justify-center gap-1.5 grow',
            candidate.status === 'assessment-sent'
              ? 'bg-info text-background hover:bg-info/90'
              : 'bg-secondary text-info hover:bg-info hover:text-background'
          )}
        >
          <SendHorizonalIcon size={16} /> {candidate.status === 'assessment-sent' ? 'Assessment Sent ✓' : 'Assessment'}
        </Button>

        {/* Note Dialog Button */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button
              variant="outline"
              aria-label="Add note"
              className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-foreground hover:text-background transition-colors flex items-center justify-center gap-1.5"
            >
              <NotebookPen size={16} /> {candidate.note ? 'Edit Note' : 'Note'}
            </Button>
          </DialogTrigger>

          <DialogContent className="border-heavy border-border bg-card p-sp-4 max-w-md text-foreground">
            <DialogHeader>
              <DialogTitle className="font-heading text-lg uppercase tracking-brutal text-foreground">
                Internal Note — {candidate.name}
              </DialogTitle>
            </DialogHeader>
            <Textarea
              value={noteInput}
              onChange={(e) => setNoteInput(e.target.value)}
              placeholder="Internal recruiter notes, feedback from technical team..."
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

        {/* Reversible workflow: Reset to Review if already decided */}
        {candidate.status && candidate.status !== 'under-review' && (
          <Button
            variant="outline"
            onClick={handleResetToReview}
            aria-label={`Reset decision for ${candidate.name} to under review`}
            className="border-thick border-muted-foreground bg-secondary text-muted-foreground uppercase tracking-brutal text-tiny font-bold px-sp-3 h-9 hover:bg-foreground hover:text-background transition-colors flex items-center justify-center gap-1.5"
            title="Revert decision back to Under Review"
          >
            <RotateCcw size={14} /> Reset
          </Button>
        )}
      </div>

      <div className="flex items-center gap-sp-2">
        <span className="text-tiny uppercase tracking-chip font-bold text-muted-foreground">Current Status:</span>
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
        <div className="mt-sp-3 border-2 border-border bg-secondary/30 p-sp-2">
          <p className="text-tiny uppercase tracking-chip font-bold mb-sp-1 text-muted-foreground">
            Recruiter Note / Reason:
          </p>
          <p className="text-small font-mono text-foreground whitespace-pre-wrap">{candidate.note}</p>
        </div>
      )}
    </div>
  );
}
