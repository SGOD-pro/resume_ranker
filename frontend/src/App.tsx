import { TooltipProvider } from '@/components/ui/tooltip';
import { AppHeader } from '@/components/layout/AppHeader';
import { ThreePanelLayout } from '@/components/layout/ThreePanelLayout';
import { BackendHealthGate } from '@/components/layout/BackendHealthGate';
import { Toaster } from '@/components/ui/toaster';
import { BlockingErrorAlert } from '@/components/layout/BlockingErrorAlert';
import { UploadProgressBar } from '@/components/layout/UploadProgressBar';

function App() {
  return (
    <BackendHealthGate>
      <TooltipProvider>
        <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
          <AppHeader />
          <UploadProgressBar />
          <ThreePanelLayout />
        </div>
        <Toaster />
        <BlockingErrorAlert />
      </TooltipProvider>
    </BackendHealthGate>
  );
}

export default App;
