import { create } from 'zustand';
import type { Candidate, Signal, CandidateStatus, UploadState } from './types';
import { mockCandidates } from './mock-data';

type SortField = 'score' | 'name';

interface CandidateStore {
  candidates: Candidate[];
  selectedId: string | null;
  filterSignal: Signal | 'all';
  sortField: SortField;
  searchQuery: string;
  showKnockouts: boolean;
  upload: UploadState;

  // Selectors
  getFilteredCandidates: () => Candidate[];
  getSelectedCandidate: () => Candidate | null;

  // Actions
  selectCandidate: (id: string) => void;
  setFilterSignal: (signal: Signal | 'all') => void;
  setSortField: (field: SortField) => void;
  setSearchQuery: (query: string) => void;
  toggleShowKnockouts: () => void;
  setStatus: (id: string, status: CandidateStatus) => void;
  setNote: (id: string, note: string) => void;
  setUpload: (upload: Partial<UploadState>) => void;
}

export const useCandidateStore = create<CandidateStore>((set, get) => ({
  candidates: mockCandidates,
  selectedId: null,
  filterSignal: 'all',
  sortField: 'score',
  searchQuery: '',
  showKnockouts: false,
  upload: {
    totalFiles: 43,
    analyzedFiles: 41,
    processingFiles: 2,
    isUploading: false,
  },

  getFilteredCandidates: () => {
    const { candidates, filterSignal, sortField, searchQuery, showKnockouts } = get();
    let filtered = [...candidates];

    // Filter by signal
    if (filterSignal !== 'all') {
      filtered = filtered.filter((c) => c.signal === filterSignal);
    }

    // Filter out knockouts unless toggled
    if (!showKnockouts) {
      filtered = filtered.filter((c) => c.signal !== 'knockout');
    }

    // Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.topSkills.some((s) => s.toLowerCase().includes(q)) ||
          c.skillMatch.matched.some((s) => s.toLowerCase().includes(q))
      );
    }

    // Sort
    if (sortField === 'score') {
      filtered.sort((a, b) => b.overallScore - a.overallScore);
    } else {
      filtered.sort((a, b) => a.name.localeCompare(b.name));
    }

    return filtered;
  },

  getSelectedCandidate: () => {
    const { candidates, selectedId } = get();
    if (!selectedId) return null;
    return candidates.find((c) => c.id === selectedId) ?? null;
  },

  selectCandidate: (id) => set({ selectedId: id }),

  setFilterSignal: (signal) => set({ filterSignal: signal }),

  setSortField: (field) => set({ sortField: field }),

  setSearchQuery: (query) => set({ searchQuery: query }),

  toggleShowKnockouts: () => set((state) => ({ showKnockouts: !state.showKnockouts })),

  setStatus: (id, status) =>
    set((state) => ({
      candidates: state.candidates.map((c) =>
        c.id === id ? { ...c, status } : c
      ),
    })),

  setNote: (id, note) =>
    set((state) => ({
      candidates: state.candidates.map((c) =>
        c.id === id ? { ...c, note } : c
      ),
    })),

  setUpload: (upload) =>
    set((state) => ({
      upload: { ...state.upload, ...upload },
    })),
}));
