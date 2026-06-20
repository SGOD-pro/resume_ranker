import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface KeywordsSectionProps {
  keywords: string[];
  onAdd: (keyword: string) => void;
  onRemove: (keyword: string) => void;
}

export function KeywordsSection({ keywords, onAdd, onRemove }: KeywordsSectionProps) {
  const [input, setInput] = useState('');

  const handleAdd = () => {
    const trimmed = input.trim();
    if (trimmed && !keywords.includes(trimmed)) {
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
        Keywords
      </Label>
      <div className="flex flex-wrap gap-sp-1 mb-sp-2">
        {keywords.map((kw) => (
          <span
            key={kw}
            className="inline-flex items-center gap-1 border-2 border-foreground bg-secondary px-3 py-sp-1 text-[10px] font-semibold uppercase tracking-chip text-foreground"
          >
            {kw}
            <button
              onClick={() => onRemove(kw)}
              className="ml-1 text-foreground hover:text-error font-bold text-xs"
              aria-label={`Remove ${kw}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <Input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="+ Add keyword"
        className="border-thick border-border bg-surface-sunken font-mono text-mono-base px-3 py-1 h-8 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
      />
    </div>
  );
}
