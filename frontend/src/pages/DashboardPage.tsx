import { ThreePanelLayout } from '@/components/layout/ThreePanelLayout';
import { UploadProgressBar } from '@/components/layout/UploadProgressBar';

export function DashboardPage() {
  return (
    <>
      <UploadProgressBar />
      <ThreePanelLayout />
    </>
  );
}
