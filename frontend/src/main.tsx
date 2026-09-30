import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

import { useAppStore } from '@/store/app-store';
import { useCandidateStore } from '@/store/candidate-store';
import { useJobStore } from '@/store/job-store';

if (import.meta.env.DEV) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).__stores = {
    useAppStore,
    useCandidateStore,
    useJobStore,
  };
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
