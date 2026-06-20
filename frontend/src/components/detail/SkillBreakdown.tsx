import type { SkillMatch } from '@/store/types';

interface SkillBreakdownProps {
  skillMatch: SkillMatch;
}

export function SkillBreakdown({ skillMatch }: SkillBreakdownProps) {
  return (
    <div>
      <h4 className="font-heading text-sm uppercase tracking-brutal mb-sp-3 text-foreground">
        Skill Breakdown
      </h4>

      {/* Matched */}
      <div className="mb-sp-3">
        <p className="text-small font-semibold mb-sp-1 text-foreground">
          ✅ Matched ({skillMatch.matched.length})
        </p>
        <div className="flex flex-wrap gap-sp-1">
          {skillMatch.matched.map((skill) => (
            <span
              key={skill}
              className="border-2 border-foreground bg-foreground text-background px-2 py-0.5 text-[10px] uppercase tracking-chip font-semibold"
            >
              {skill}
            </span>
          ))}
        </div>
      </div>

      {/* Missing */}
      {skillMatch.missing.length > 0 && (
        <div className="mb-sp-3">
          <p className="text-small font-semibold mb-sp-1 text-foreground">
            ❌ Missing ({skillMatch.missing.length})
          </p>
          <div className="flex flex-wrap gap-sp-1">
            {skillMatch.missing.map((skill) => (
              <span
                key={skill}
                className="border-2 border-error bg-background text-error px-2 py-0.5 text-[10px] uppercase tracking-chip font-semibold"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Extra */}
      {skillMatch.extra.length > 0 && (
        <div>
          <p className="text-small font-semibold mb-sp-1 text-foreground">
            ➕ Extra ({skillMatch.extra.length})
          </p>
          <div className="flex flex-wrap gap-sp-1">
            {skillMatch.extra.map((skill) => (
              <span
                key={skill}
                className="border-2 border-muted-foreground bg-background text-muted-foreground px-2 py-0.5 text-[10px] uppercase tracking-chip font-semibold"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
