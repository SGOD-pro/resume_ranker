import { create } from 'zustand';
import type { Candidate, Signal, CandidateStatus, UploadState } from './types';
import { useJobStore } from './job-store';

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
  setCandidates: (candidates: Candidate[]) => void;
  setStatus: (id: string, status: CandidateStatus) => void;
  setNote: (id: string, note: string) => void;
  setUpload: (upload: Partial<UploadState>) => void;
}

export const useCandidateStore = create<CandidateStore>((set, get) => ({
  candidates: [],
  selectedId: null,
  filterSignal: 'all',
  sortField: 'score',
  searchQuery: '',
  showKnockouts: false,
  upload: {
    totalFiles: 0,
    analyzedFiles: 0,
    processingFiles: 0,
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

    // Dynamic Score Recalculation
    const weights = useJobStore.getState().job.weights;
    const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0) || 100;
    
    // Recalculate score for sorting
    filtered = filtered.map(c => {
      // Base score components (0-100 each)
      const baseScore = 
        (c.scoreBreakdown.skills * (weights.skills / totalWeight)) +
        (c.scoreBreakdown.experience * (weights.experience / totalWeight)) +
        (c.scoreBreakdown.keywords * (weights.keywords / totalWeight)) +
        (c.scoreBreakdown.education * (weights.education / totalWeight));
      
      // We keep the exact backend penalties relative by figuring out how much the backend reduced/added to the old base score, 
      // but for client-side recompute, a simpler direct mapping is usually sufficient for visual resorting.
      // We will use the dynamically computed base score. If backend sends knockout, it's 0.
      const dynamicScore = c.signal === 'knockout' ? 0 : Math.round(baseScore * 10) / 10;
      
      return { ...c, overallScore: dynamicScore };
    });

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
    const c = candidates.find((c) => c.id === selectedId);
    if (!c) return null;

    // Dynamic Score Recalculation
    const weights = useJobStore.getState().job.weights;
    const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0) || 100;
    
    const baseScore = 
      (c.scoreBreakdown.skills * (weights.skills / totalWeight)) +
      (c.scoreBreakdown.experience * (weights.experience / totalWeight)) +
      (c.scoreBreakdown.keywords * (weights.keywords / totalWeight)) +
      (c.scoreBreakdown.education * (weights.education / totalWeight));
    
    const dynamicScore = c.signal === 'knockout' ? 0 : Math.round(baseScore * 10) / 10;
    
    return { ...c, overallScore: dynamicScore };
  },

  setCandidates: (candidates) => set({ candidates, selectedId: null }),

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
