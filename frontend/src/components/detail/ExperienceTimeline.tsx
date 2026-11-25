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
        {experience.length === 0 ? (
          <p className="text-tiny font-mono text-muted-foreground italic">No experience records detected</p>
        ) : (
          experience.map((entry) => {
            const dateStr = entry.startDate && entry.endDate
              ? `${entry.startDate} — ${entry.endDate}`
              : (entry.startDate || entry.endDate || '');
            const durStr = entry.durationYears > 0 ? ` (${entry.durationYears}yr)` : '';
            return (
              <div key={entry.id} className="border-l-heavy border-foreground pl-sp-3">
                <p className="text-sm font-semibold text-foreground">
                  {[entry.role, entry.company].filter(Boolean).join(' · ')}
                </p>
                {(dateStr || durStr) && (
                  <p className="text-tiny font-mono text-muted-foreground mt-sp-1">
                    {dateStr}{durStr}
                  </p>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
