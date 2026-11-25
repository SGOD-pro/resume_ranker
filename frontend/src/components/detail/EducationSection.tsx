import type { EducationEntry } from '@/store/types';

interface EducationSectionProps {
  education: EducationEntry[];
}

export function EducationSection({ education }: EducationSectionProps) {
  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Education
      </h4>
      <div className="space-y-sp-3">
        {education.length === 0 ? (
          <p className="text-tiny font-mono text-muted-foreground italic">No education records detected</p>
        ) : (
          education.map((entry) => {
            const subtitle = [entry.institution, entry.yearRange].filter(Boolean).join(' · ');
            return (
              <div key={entry.id} className="border-l-heavy border-foreground pl-sp-3">
                <p className="text-sm font-semibold text-foreground">
                  {entry.degree}{entry.field ? ` - ${entry.field}` : ''}
                </p>
                {subtitle && (
                  <p className="text-tiny font-mono text-muted-foreground mt-sp-1">
                    {subtitle}
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
