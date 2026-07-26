import { useMemo } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { ResumeUploadZone } from './ResumeUploadZone';
import { CandidateFilters } from './CandidateFilters';
import { CandidateRow } from './CandidateRow';
import { CandidateListFooter } from './CandidateListFooter';
import { CenterPanelLoader } from './CenterPanelLoader';
import { useCandidateStore } from '@/store/candidate-store';
import { useAppStore } from '@/store/app-store';
import { useWeightsStore } from '@/store/weights-store';
import { useJobCandidates } from '@/hooks/useV2Queries';
import { useJobUpdates } from '@/hooks/useJobUpdates';
import type { Candidate } from '@/store/types';

interface RawCandidate {
  id?: string;
  name?: string;
  candidate_id?: string;
  extraction?: {
    explicit_skills?: { name: string }[];
  };
  skillMatch?: { matched: string[]; missing: string[]; extra: string[] };
  signal?: string;
  skill_score?: number;
  experience_score?: number;
  education_score?: number;
  semantic_score?: number;
  flags?: any[];
}

export function CandidateListPanel() {
  const filterSignal = useCandidateStore((s) => s.filterSignal);
  const sortField = useCandidateStore((s) => s.sortField);
  const searchQuery = useCandidateStore((s) => s.searchQuery);
  const showKnockouts = useCandidateStore((s) => s.showKnockouts);
  const appPhase = useAppStore((s) => s.appPhase);
  const jobId = useAppStore((s) => s.jobId);
  const computeComposite = useWeightsStore((s) => s.computeComposite);
  
  // Connect to WebSocket updates
  useJobUpdates(jobId);

  // Fetch candidates from V2 API
  const { data: queryData, isLoading } = useJobCandidates(jobId);

  const candidates = useMemo(() => {
    const rawCandidates = queryData?.candidates || [];
    let filtered = rawCandidates.map((c: unknown) => {
      const rc = c as RawCandidate;
      return {
        ...rc,
        id: rc.id || rc.candidate_id || Math.random().toString(),
        rank: 0,
        overallScore: computeComposite(rc),
        // mapping backend data to frontend expected properties if needed
        name: rc.name || rc.candidate_id || 'Unknown',
        title: '',
        location: '',
        email: '',
        phone: '',
        pdfUrl: '',
        totalYears: 0,
        status: 'under-review',
        note: '',
        scoreBreakdown: {
          skills: rc.skill_score || 0,
          experience: rc.experience_score || 0,
          keywords: rc.semantic_score || 0,
          education: rc.education_score || 0,
        },
        experience: [],
        education: [],
        knockoutChecks: [],
        topSkills: rc.extraction?.explicit_skills?.map((s: { name: string }) => s.name) || [],
        skillMatch: rc.skillMatch || { matched: [], missing: [], extra: [] },
        signal: rc.signal || 'processing',
        flags: rc.flags || [],
      } as unknown as Candidate;
    });

    if (filterSignal !== 'all') {
      filtered = filtered.filter((c) => c.signal === filterSignal);
    }

    if (!showKnockouts) {
      filtered = filtered.filter((c) => c.signal !== 'knockout');
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          (c.topSkills && c.topSkills.some((s: string) => s.toLowerCase().includes(q)))
      );
    }

    if (sortField === 'score') {
      filtered.sort((a, b) => b.overallScore - a.overallScore);
    } else {
      filtered.sort((a, b) => a.name.localeCompare(b.name));
    }

    return filtered;
  }, [queryData?.candidates, filterSignal, sortField, searchQuery, showKnockouts, computeComposite]);

  const showLoader = appPhase === 'extracting' || appPhase === 'scoring' || isLoading;

  return (
    <div className="flex h-full flex-col">
      <div className="p-sp-4 pb-0">
        <ResumeUploadZone />
        <Separator className="bg-border h-[3px] my-sp-3" />
        <CandidateFilters />
      </div>

      <Separator className="bg-border h-[3px]" />

      {showLoader && candidates.length === 0 ? (
        <CenterPanelLoader phase={appPhase} />
      ) : candidates.length === 0 && !jobId ? (
        <div className="flex-1 flex flex-col items-center justify-center p-sp-5 gap-sp-3">
          <p className="font-heading text-2xl uppercase tracking-brutal text-foreground text-center">
            No Results Yet
          </p>
          <p className="text-small text-muted-foreground font-mono text-center max-w-xs">
            Upload resumes and analyze them against a Job Description to generate rankings.
          </p>
        </div>
      ) : (
        <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
          <div className="flex items-center gap-sp-2 px-sp-4 py-sp-2 bg-secondary text-foreground shrink-0">
            <span className="w-8 text-tiny uppercase tracking-chip font-bold">#</span>
            <span className="flex-1 text-tiny uppercase tracking-chip font-bold">Name</span>
            <span className="w-16 text-tiny uppercase tracking-chip font-bold text-right">Score</span>
            <span className="w-20 text-tiny uppercase tracking-chip font-bold text-right">Signal</span>
          </div>

          <ScrollArea className="flex-1 scrollbar-brutal pb-10 h-full">
            <div>
              {candidates.map((candidate, idx) => (
                <CandidateRow key={candidate.id || idx} candidate={candidate} />
              ))}
              {candidates.length === 0 && (
                <div className="p-sp-5 text-center text-muted-foreground text-small">
                  No candidates match the current filters.
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}

      <Separator className="bg-border h-[3px]" />
      <CandidateListFooter />
    </div>
  );
}
