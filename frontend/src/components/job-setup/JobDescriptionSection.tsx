import { useRef, useState } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useJobStore } from '@/store/job-store';
import { toast } from 'sonner';
import { Loader2, UploadCloud } from 'lucide-react';

export function JobDescriptionSection() {
  const { job, setDescription } = useJobStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('Only PDF files are supported.');
      return;
    }

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    try {
      const res = await fetch(`${apiBase}/api/v2/jobs/parse-jd`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      if (data.text) {
        setDescription(data.text);
        toast.success(`Job Description loaded from ${file.name}`);
      } else {
        toast.warning('No text could be extracted from this PDF.');
      }
    } catch (err) {
      toast.error('Failed to parse JD PDF: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div>
      <Label className="font-heading text-sm uppercase tracking-chip mb-sp-1 block text-foreground">
        Job Description
      </Label>
      <Textarea
        value={job.description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Paste JD here..."
        rows={6}
        className="border-thick border-border bg-surface-sunken font-mono text-mono-base p-3 resize-y text-foreground placeholder:text-muted-foreground focus:border-heavy focus:border-foreground focus:outline-none"
      />
      <div className="mt-sp-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleFileChange}
        />
        <Button
          type="button"
          variant="outline"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
          className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-small font-semibold px-sp-3 py-sp-1 h-8 hover:bg-foreground hover:text-background transition-colors flex items-center gap-1.5 cursor-pointer"
        >
          {isUploading ? (
            <>
              <Loader2 className="animate-spin" size={14} />
              Extracting JD…
            </>
          ) : (
            <>
              <UploadCloud size={14} />
              Upload JD PDF
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
