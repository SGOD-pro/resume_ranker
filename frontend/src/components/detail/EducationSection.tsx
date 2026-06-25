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
        {education.map((entry) => (
          <div key={entry.id} className="border-l-heavy border-foreground pl-sp-3">
            <p className="text-sm font-semibold text-foreground">
              {entry.degree} - {entry.field}
            </p>
            <p className="text-tiny font-mono text-muted-foreground mt-sp-1">
              {entry.institution} · {entry.yearRange}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
