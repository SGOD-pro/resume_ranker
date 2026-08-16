import { useMemo } from 'react';
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
import { useJobStore } from '@/store/job-store';


export function CandidateDetailPanel() {
  // ── Use stable primitive selectors — never call computed functions as selectors.
  // Calling s.getSelectedCandidate() as a selector returns a new object every
  // render (due to { ...c, overallScore }) which breaks Zustand's getSnapshot
  // cache and causes an infinite re-render loop.
  const selectedId  = useCandidateStore((s) => s.selectedId);
  const candidates  = useCandidateStore((s) => s.candidates);
  const jobWeights  = useJobStore((s) => s.job.weights);

  // Compute the candidate with dynamic score inside useMemo so the reference
  // is stable and only recalculates when the selected id, list, or weights change.
  const candidate = useMemo(() => {
    if (!selectedId) return null;
    const c = candidates.find((c) => c.id === selectedId);
    if (!c) return null;
    const totalWeight = Object.values(jobWeights).reduce((a, b) => a + b, 0) || 100;
    const sb = c.scoreBreakdown ?? { skills: 0, experience: 0, keywords: 0, education: 0 };
    const baseScore =
      (sb.skills     * (jobWeights.skills     / totalWeight)) +
      (sb.experience * (jobWeights.experience / totalWeight)) +
      (sb.keywords   * (jobWeights.keywords   / totalWeight)) +
      (sb.education  * (jobWeights.education  / totalWeight));
    const dynamicScore = c.signal === 'knockout' ? 0 : Math.round(baseScore * 10) / 10;
    return { ...c, overallScore: dynamicScore };
  }, [selectedId, candidates, jobWeights]);

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
