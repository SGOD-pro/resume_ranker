import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AppHeader } from '@/components/layout/AppHeader';
import { BackendHealthGate } from '@/components/layout/BackendHealthGate';
import { Toaster } from '@/components/ui/toaster';
import { BlockingErrorAlert } from '@/components/layout/BlockingErrorAlert';
import { DashboardPage } from '@/pages/DashboardPage';
import { AtsCheckerPage } from '@/pages/AtsCheckerPage';

function App() {
  return (
    <BrowserRouter>
      <BackendHealthGate>
        <TooltipProvider>
          <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
            <AppHeader />
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/ats-checker" element={<AtsCheckerPage />} />
            </Routes>
          </div>
          <Toaster />
          <BlockingErrorAlert />
        </TooltipProvider>
      </BackendHealthGate>
    </BrowserRouter>
  );
}

export default App;
