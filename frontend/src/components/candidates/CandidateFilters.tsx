import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCandidateStore } from '@/store/candidate-store';
import type { Signal } from '@/store/types';

const signalOptions: { value: Signal | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'strong', label: 'Strong' },
  { value: 'good', label: 'Good' },
  { value: 'fair', label: 'Fair' },
  { value: 'knockout', label: 'Knockout' },
];

const sortOptions = [
  { value: 'score', label: 'Score' },
  { value: 'name', label: 'Name' },
];

export function CandidateFilters() {
  const { filterSignal, sortField, searchQuery, setFilterSignal, setSortField, setSearchQuery } =
    useCandidateStore();

  return (
    <div className="flex flex-wrap items-center gap-sp-2 mb-sp-3">
      <div className="flex items-center gap-sp-1">
        <span className="text-tiny uppercase tracking-chip font-bold text-muted-foreground">Filter:</span>
        <Select
          value={filterSignal}
          onValueChange={(val) => setFilterSignal(val as Signal | 'all')}
        >
          <SelectTrigger className="border-thick border-border bg-surface-sunken font-mono text-tiny h-8 w-24 px-2 text-foreground focus:border-heavy focus:border-foreground">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="border-thick border-border bg-card text-foreground">
            {signalOptions.map((opt) => (
              <SelectItem
                key={opt.value}
                value={opt.value}
                className="font-mono text-tiny hover:bg-foreground hover:text-background cursor-pointer"
              >
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-sp-1">
        <span className="text-tiny uppercase tracking-chip font-bold text-muted-foreground">Sort:</span>
        <Select
          value={sortField}
          onValueChange={(val) => setSortField(val as 'score' | 'name')}
        >
          <SelectTrigger className="border-thick border-border bg-surface-sunken font-mono text-tiny h-8 w-24 px-2 text-foreground focus:border-heavy focus:border-foreground">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="border-thick border-border bg-card text-foreground">
            {sortOptions.map((opt) => (
              <SelectItem
                key={opt.value}
                value={opt.value}
                className="font-mono text-tiny hover:bg-foreground hover:text-background cursor-pointer"
              >
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1 min-w-[120px]">
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="name or skill..."
          className="border-thick border-border bg-surface-sunken font-mono text-tiny h-8 px-2 text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
        />
      </div>
    </div>
  );
}
