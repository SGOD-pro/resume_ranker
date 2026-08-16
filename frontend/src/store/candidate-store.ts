/**
 * candidate-store.ts — Zustand store for candidate state
 * ========================================================
 * IMPORTANT: Do NOT add computed selectors that return new objects (like
 * getSelectedCandidate / getFilteredCandidates used to do). Zustand uses
 * Object.is() to compare snapshots — returning a new { ...spread } object
 * on every call breaks getSnapshot caching and causes an infinite render loop.
 *
 * Pattern to follow:
 *   ✅ useCandidateStore((s) => s.selectedId)          — primitive, stable
 *   ✅ const result = useMemo(() => compute(raw), [...]) — derived in component
 *   ❌ useCandidateStore((s) => s.getSelectedCandidate()) — new object every call
 */

import { create } from 'zustand';
import type { Candidate, Signal, CandidateStatus, UploadState } from './types';

type SortField = 'score' | 'name';

interface CandidateStore {
  candidates: Candidate[];
  selectedId: string | null;
  filterSignal: Signal | 'all';
  sortField: SortField;
  searchQuery: string;
  showKnockouts: boolean;
  upload: UploadState;

  // Actions (only primitive state mutations — no computed selectors)
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

export const useCandidateStore = create<CandidateStore>((set) => ({
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
