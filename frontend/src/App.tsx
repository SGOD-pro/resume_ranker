import { TooltipProvider } from '@/components/ui/tooltip';
import { AppHeader } from '@/components/layout/AppHeader';
import { ThreePanelLayout } from '@/components/layout/ThreePanelLayout';

function App() {
  return (
    <TooltipProvider>
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
        <AppHeader />
        <ThreePanelLayout />
      </div>
    </TooltipProvider>
  );
}

export default App;
