import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { CandidateHeader } from './CandidateHeader';
import { MatchScoreSection } from './MatchScoreSection';
import { SkillBreakdown } from './SkillBreakdown';
import { KnockoutChecks } from './KnockoutChecks';
import { ExperienceTimeline } from './ExperienceTimeline';
import { EducationSection } from './EducationSection';
import { FlagsSection } from './FlagsSection';
import { CandidateActions } from './CandidateActions';
import { useCandidateStore } from '@/store/candidate-store';

export function CandidateDetailPanel() {
  const selectedId = useCandidateStore((s) => s.selectedId);
  const candidates = useCandidateStore((s) => s.candidates);
  const candidate = selectedId ? candidates.find((c) => c.id === selectedId) ?? null : null;

  if (!candidate) {
    return (
      <div className="flex h-full items-center justify-center p-sp-5">
        <div className="text-center">
          <p className="font-heading text-2xl uppercase tracking-brutal mb-sp-2 text-foreground">
            No Candidate Selected
          </p>
          <p className="text-small text-muted-foreground font-mono">
            Click a candidate from the list to view details.
          </p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="h-full scrollbar-brutal">
      <div className="p-sp-4">
        <CandidateHeader candidate={candidate} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        <MatchScoreSection candidate={candidate} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        <SkillBreakdown skillMatch={candidate.skillMatch} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        <KnockoutChecks checks={candidate.knockoutChecks} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        <ExperienceTimeline experience={candidate.experience} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        <EducationSection education={candidate.education} />

        {candidate.flags.length > 0 && (
          <>
            <Separator className="bg-border h-[3px] my-sp-4" />
            <FlagsSection flags={candidate.flags} />
          </>
        )}

        <Separator className="bg-border h-[3px] my-sp-4" />

        <CandidateActions candidate={candidate} />
      </div>
    </ScrollArea>
  );
}
