import type { ExperienceEntry } from '@/store/types';

interface ExperienceTimelineProps {
  experience: ExperienceEntry[];
}

export function ExperienceTimeline({ experience }: ExperienceTimelineProps) {
  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Experience
      </h4>
      <div className="space-y-sp-3">
        {experience.map((entry) => (
          <div key={entry.id} className="border-l-heavy border-foreground pl-sp-3">
            <p className="text-sm font-semibold text-foreground">
              {entry.role} · {entry.company}
            </p>
            <p className="text-tiny font-mono text-muted-foreground mt-sp-1">
              {entry.startDate} – {entry.endDate} ({entry.durationYears}yr)
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
