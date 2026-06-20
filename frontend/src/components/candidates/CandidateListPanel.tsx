import { useMemo } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { ResumeUploadZone } from './ResumeUploadZone';
import { CandidateFilters } from './CandidateFilters';
import { CandidateRow } from './CandidateRow';
import { CandidateListFooter } from './CandidateListFooter';
import { useCandidateStore } from '@/store/candidate-store';

export function CandidateListPanel() {
  const allCandidates = useCandidateStore((s) => s.candidates);
  const filterSignal = useCandidateStore((s) => s.filterSignal);
  const sortField = useCandidateStore((s) => s.sortField);
  const searchQuery = useCandidateStore((s) => s.searchQuery);
  const showKnockouts = useCandidateStore((s) => s.showKnockouts);

  const candidates = useMemo(() => {
    let filtered = [...allCandidates];

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
          c.topSkills.some((s) => s.toLowerCase().includes(q)) ||
          c.skillMatch.matched.some((s) => s.toLowerCase().includes(q))
      );
    }

    if (sortField === 'score') {
      filtered.sort((a, b) => b.overallScore - a.overallScore);
    } else {
      filtered.sort((a, b) => a.name.localeCompare(b.name));
    }

    return filtered;
  }, [allCandidates, filterSignal, sortField, searchQuery, showKnockouts]);

  return (
    <div className="flex h-full flex-col">
      <div className="p-sp-4 pb-0">
        <ResumeUploadZone />
        <Separator className="bg-border h-[3px] my-sp-3" />
        <CandidateFilters />
      </div>

      <Separator className="bg-border h-[3px]" />

      {/* Table header */}
      <div className="flex items-center gap-sp-2 px-sp-4 py-sp-2 bg-foreground text-background">
        <span className="w-8 text-tiny uppercase tracking-chip font-bold">#</span>
        <span className="flex-1 text-tiny uppercase tracking-chip font-bold">Name</span>
        <span className="w-16 text-tiny uppercase tracking-chip font-bold text-right">Score</span>
        <span className="w-20 text-tiny uppercase tracking-chip font-bold text-right">Signal</span>
      </div>

      <ScrollArea className="flex-1 scrollbar-brutal">
        <div>
          {candidates.map((candidate) => (
            <CandidateRow key={candidate.id} candidate={candidate} />
          ))}
          {candidates.length === 0 && (
            <div className="p-sp-5 text-center text-muted-foreground text-small">
              No candidates match the current filters.
            </div>
          )}
        </div>
      </ScrollArea>

      <Separator className="bg-border h-[3px]" />
      <CandidateListFooter />
    </div>
  );
}
