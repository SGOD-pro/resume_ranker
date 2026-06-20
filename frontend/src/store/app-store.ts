/**
 * app-store.ts — App-level UI state
 * ===================================
 * Drives the cold-start gate, upload progress bar, center panel loader,
 * and blocking error overlay. All components read from here.
 */

import { create } from 'zustand';

export type BackendStatus = 'checking' | 'waking-up' | 'ready' | 'unreachable';
export type AppPhase = 'idle' | 'uploading' | 'extracting' | 'scoring' | 'complete';

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
  currentFile: string;
  filesUploaded: number;
  filesTotal: number;
}

export interface BlockingError {
  title: string;
  message: string;
  onRetry?: () => void;
}

interface AppStore {
  backendStatus: BackendStatus;
  appPhase: AppPhase;
  uploadProgress: UploadProgress;
  sseRetryCount: number;
  blockingError: BlockingError | null;
  jobId: string | null;

  setBackendStatus: (status: BackendStatus) => void;
  setAppPhase: (phase: AppPhase) => void;
  setUploadProgress: (progress: Partial<UploadProgress>) => void;
  resetUploadProgress: () => void;
  setSseRetryCount: (count: number) => void;
  setBlockingError: (error: BlockingError | null) => void;
  setJobId: (id: string | null) => void;
}

const defaultUploadProgress: UploadProgress = {
  loaded: 0,
  total: 0,
  percent: 0,
  currentFile: '',
  filesUploaded: 0,
  filesTotal: 0,
};

export const useAppStore = create<AppStore>((set) => ({
  backendStatus: 'checking',
  appPhase: 'idle',
  uploadProgress: { ...defaultUploadProgress },
  sseRetryCount: 0,
  blockingError: null,
  jobId: null,

  setBackendStatus: (status) => set({ backendStatus: status }),
  setAppPhase: (phase) => set({ appPhase: phase }),
  setUploadProgress: (progress) =>
    set((state) => ({
      uploadProgress: { ...state.uploadProgress, ...progress },
    })),
  resetUploadProgress: () =>
    set({ uploadProgress: { ...defaultUploadProgress } }),
  setSseRetryCount: (count) => set({ sseRetryCount: count }),
  setBlockingError: (error) => set({ blockingError: error }),
  setJobId: (id) => set({ jobId: id }),
}));
