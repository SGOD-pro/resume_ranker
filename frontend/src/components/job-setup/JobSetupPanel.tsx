import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { JobInfoSection } from './JobInfoSection';
import { JobDescriptionSection } from './JobDescriptionSection';
import { SkillTagsSection } from './SkillTagsSection';
import { ExperienceSection } from './ExperienceSection';
import { EducationSection } from './EducationSection';
import { KeywordsSection } from './KeywordsSection';
import { WeightsSection } from './WeightsSection';
import { AnalyzeButton } from './AnalyzeButton';
import { useJobStore } from '@/store/job-store';
import { useAppStore } from '@/store/app-store';

export function JobSetupPanel() {
  const {
    addMustHaveSkill,
    removeMustHaveSkill,
    addNiceToHaveSkill,
    removeNiceToHaveSkill,
    addKeyword,
    removeKeyword,
    job,
  } = useJobStore();

  const appPhase = useAppStore((s) => s.appPhase);
  const isLocked = appPhase === 'extracting' || appPhase === 'scoring';

  return (
    <ScrollArea className="h-full scrollbar-brutal">
      <div className="p-sp-4">
        <h3 className="font-heading text-lg uppercase tracking-brutal mb-sp-4 text-foreground">
          + New Job Opening
        </h3>

        <Separator className="bg-border h-[3px] mb-sp-4" />

        {/* Form content — disabled (locked) once analysis starts */}
        <div className={isLocked ? 'panel-disabled' : ''}>
          <JobInfoSection />

          <Separator className="bg-border h-px my-sp-4" />

          <JobDescriptionSection />

          <Separator className="bg-border h-px my-sp-4" />

          <SkillTagsSection
            title="Must-Have Skills"
            skills={job.mustHaveSkills}
            onAdd={addMustHaveSkill}
            onRemove={removeMustHaveSkill}
          />

          <Separator className="bg-border h-px my-sp-4" />

          <SkillTagsSection
            title="Nice-to-Have"
            skills={job.niceToHaveSkills}
            onAdd={addNiceToHaveSkill}
            onRemove={removeNiceToHaveSkill}
          />

          <Separator className="bg-border h-px my-sp-4" />

          <ExperienceSection />

          <Separator className="bg-border h-px my-sp-4" />

          <EducationSection />

          <Separator className="bg-border h-px my-sp-4" />

          <KeywordsSection
            keywords={job.keywords}
            onAdd={addKeyword}
            onRemove={removeKeyword}
          />

          <Separator className="bg-border h-px my-sp-4" />

          <WeightsSection />
        </div>

        {/* Analyze button stays interactive (handles its own disable state) */}
        <div className="mt-sp-5">
          <AnalyzeButton />
        </div>
      </div>
    </ScrollArea>
  );
}
