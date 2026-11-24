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
  selectedJobId: string | null;
  filterSignal: Signal | 'all';
  sortField: SortField;
  searchQuery: string;
  showKnockouts: boolean;
  upload: UploadState;

  // Actions (only primitive state mutations — no computed selectors)
  selectCandidate: (id: string | null, jobId?: string | null) => void;
  setFilterSignal: (signal: Signal | 'all') => void;
  setSortField: (field: SortField) => void;
  setSearchQuery: (query: string) => void;
  toggleShowKnockouts: () => void;
  setCandidates: (candidates: Candidate[], jobId?: string | null) => void;
  setStatus: (id: string, status: CandidateStatus) => void;
  setNote: (id: string, note: string) => void;
  setUpload: (upload: Partial<UploadState>) => void;
}

function getInitialSelectedId(jobId?: string | null): string | null {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      const activeJobId = jobId || sessionStorage.getItem('active_job_id');
      if (activeJobId) {
        return sessionStorage.getItem(`selected_candidate_${activeJobId}`);
      }
    }
  } catch (err) {
    void err;
  }
  return null;
}

export const useCandidateStore = create<CandidateStore>((set) => ({
  candidates: [],
  selectedId: getInitialSelectedId(),
  selectedJobId: null,
  filterSignal: 'all',
  sortField: 'score',
  searchQuery: '',
  showKnockouts: true,
  upload: {
    totalFiles: 0,
    analyzedFiles: 0,
    processingFiles: 0,
    isUploading: false,
  },

  setCandidates: (candidates, jobId) =>
    set((state) => {
      const activeJobId =
        jobId ||
        state.selectedJobId ||
        (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('active_job_id') : null);
      let targetId = state.selectedId;
      if (activeJobId && typeof sessionStorage !== 'undefined') {
        const storedForJob = sessionStorage.getItem(`selected_candidate_${activeJobId}`);
        if (storedForJob) {
          targetId = storedForJob;
        } else if (state.selectedJobId && state.selectedJobId !== activeJobId) {
          targetId = null;
        }
      }
      const validSelectedId =
        targetId && candidates.some((c) => c.id === targetId)
          ? targetId
          : null;
      try {
        if (activeJobId && typeof sessionStorage !== 'undefined') {
          if (validSelectedId) {
            sessionStorage.setItem(`selected_candidate_${activeJobId}`, validSelectedId);
          } else {
            sessionStorage.removeItem(`selected_candidate_${activeJobId}`);
          }
        }
      } catch (err) {
        void err;
      }
      return {
        candidates,
        selectedId: validSelectedId,
        selectedJobId: activeJobId,
      };
    }),

  selectCandidate: (id, jobId) => {
    try {
      const activeJobId =
        jobId ||
        (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('active_job_id') : null);
      if (activeJobId && typeof sessionStorage !== 'undefined') {
        if (id) {
          sessionStorage.setItem(`selected_candidate_${activeJobId}`, id);
        } else {
          sessionStorage.removeItem(`selected_candidate_${activeJobId}`);
        }
      }
    } catch (err) {
      void err;
    }
    set({ selectedId: id });
  },

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
