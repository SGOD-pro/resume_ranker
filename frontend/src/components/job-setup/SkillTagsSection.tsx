import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface SkillTagsSectionProps {
  title: string;
  skills: string[];
  onAdd: (skill: string) => void;
  onRemove: (skill: string) => void;
}

export function SkillTagsSection({ title, skills, onAdd, onRemove }: SkillTagsSectionProps) {
  const [input, setInput] = useState('');

  const handleAdd = () => {
    const trimmed = input.trim();
    if (trimmed && !skills.includes(trimmed)) {
      onAdd(trimmed);
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <div>
      <Label className="font-heading text-sm uppercase tracking-chip mb-sp-2 block text-foreground">
        {title}
      </Label>
      <div className="flex flex-wrap gap-sp-1 mb-sp-2">
        {skills.map((skill) => (
          <span
            key={skill}
            className="inline-flex items-center gap-1 border-2 border-foreground bg-secondary px-3 py-sp-1 text-[10px] font-semibold uppercase tracking-chip text-foreground"
          >
            {skill}
            <button
              onClick={() => onRemove(skill)}
              className="ml-1 text-foreground hover:text-error font-bold text-xs"
              aria-label={`Remove ${skill}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-sp-1">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`+ Add ${title.toLowerCase().includes('skill') ? 'skill' : 'item'}`}
          className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-1 h-8 flex-1 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
        />
      </div>
    </div>
  );
}
