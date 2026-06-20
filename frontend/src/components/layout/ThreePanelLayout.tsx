import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable';
import { JobSetupPanel } from '@/components/job-setup/JobSetupPanel';
import { CandidateListPanel } from '@/components/candidates/CandidateListPanel';
import { CandidateDetailPanel } from '@/components/detail/CandidateDetailPanel';

export function ThreePanelLayout() {
  return (
    <div className="flex-1 overflow-hidden">
      <ResizablePanelGroup
        orientation="horizontal"
        
        className="h-full"
        id="rawblock-layout"
      >
        {/* LEFT — Job Setup */}
        <ResizablePanel id="left-panel" defaultSize={"25%"} >
          <div className="h-full min-h-0 min-w-0 overflow-hidden">
            <JobSetupPanel />
          </div>
        </ResizablePanel>

        <ResizableHandle className="w-[3px] bg-border hover:bg-foreground transition-colors cursor-col-resize" />

        {/* CENTER — Candidate List */}
        <ResizablePanel id="center-panel" defaultSize={"50%"} >
          <div className="h-full overflow-hidden">
            <CandidateListPanel />
          </div>
        </ResizablePanel>

        <ResizableHandle className="w-[3px] bg-border hover:bg-foreground transition-colors cursor-col-resize" />

        {/* RIGHT — Candidate Detail */}
        <ResizablePanel id="right-panel" defaultSize={"25%"} >
          <div className="h-full overflow-hidden">
            <CandidateDetailPanel />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
