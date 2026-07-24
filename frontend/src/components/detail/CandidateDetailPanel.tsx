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
import { useAppStore } from '@/store/app-store';
import { useCandidateDetail } from '@/hooks/useV2Queries';
import { PdfAtsViewer } from './PdfAtsViewer';
import type { Candidate } from '@/store/types';
import type { BoundingBox } from '@/lib/api-v2';

export function CandidateDetailPanel() {
  const selectedId = useCandidateStore((s) => s.selectedId);
  const jobId = useAppStore((s) => s.jobId);

  const { data: candidateDetail, isLoading } = useCandidateDetail(jobId, selectedId);

  // We fallback to standard candidate mock format for unchanged subcomponents
  // In a real app we'd refactor CandidateHeader etc to take the new V2CandidateDetailResponse format
  const candidate = candidateDetail as unknown as Candidate | null;

  if (isLoading && selectedId) {
    return (
      <div className="flex h-full items-center justify-center p-sp-5 animate-pulse">
        Loading details...
      </div>
    );
  }

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

  // Safely extract the V2 PDF info
  const pdfUrl = (candidateDetail as Record<string, unknown>)?.url as string || candidate.pdfUrl;
  const boundingBoxes = ((candidateDetail as Record<string, unknown>)?.ats_result as Record<string, unknown>)?.bounding_boxes as BoundingBox[] || [];

  return (
    <ScrollArea className="h-full scrollbar-brutal">
      <div className="p-sp-4">
        {/* Some subcomponents might need minor prop mapping here if V2 model drifted from V1 */}
        <CandidateHeader candidate={candidate} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        <MatchScoreSection candidate={candidate} />

        <Separator className="bg-border h-[3px] my-sp-4" />

        {candidate.skillMatch && (
          <>
            <SkillBreakdown skillMatch={candidate.skillMatch} />
            <Separator className="bg-border h-[3px] my-sp-4" />
          </>
        )}

        {candidate.knockoutChecks && (
          <>
            <KnockoutChecks checks={candidate.knockoutChecks} />
            <Separator className="bg-border h-[3px] my-sp-4" />
          </>
        )}

        {candidate.experience && (
          <>
            <ExperienceTimeline experience={candidate.experience} />
            <Separator className="bg-border h-[3px] my-sp-4" />
          </>
        )}

        {candidate.education && (
          <>
            <EducationSection education={candidate.education} />
            <Separator className="bg-border h-[3px] my-sp-4" />
          </>
        )}

        {candidate.flags && candidate.flags.length > 0 && (
          <>
            <FlagsSection flags={candidate.flags} />
            <Separator className="bg-border h-[3px] my-sp-4" />
          </>
        )}

        <CandidateActions candidate={candidate} />

        {pdfUrl && (
          <PdfAtsViewer pdfUrl={pdfUrl} boundingBoxes={boundingBoxes} />
        )}
      </div>
    </ScrollArea>
  );
}
