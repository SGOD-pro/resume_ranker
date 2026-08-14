import { useState } from 'react';
import { PdfViewer, type BoundingBox } from '@/components/ui/PdfViewer';
import { Loader2, UploadCloud, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

interface AtsCheckResponse {
  score: number;
  breakdown: Record<string, number>;
  flags: string[];
  boundingBoxes: BoundingBox[];
}

export function AtsCheckerPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AtsCheckResponse | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    if (selected.type !== 'application/pdf') {
      toast.error('Only PDF files are supported.');
      return;
    }

    setFile(selected);
    setIsLoading(true);
    setResult(null);

    const formData = new FormData();
    formData.append('file', selected);

    try {
      const res = await fetch('http://localhost:8000/api/v2/jobs/ats-check', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Failed to run ATS check');
      
      const data = await res.json();
      setResult(data);
    } catch (error) {
      toast.error('An error occurred during ATS checking.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 flex flex-col">
      <div className="mx-auto max-w-6xl w-full flex-1 flex flex-col">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight mb-2">ATS Checker</h1>
          <p className="text-muted-foreground">
            Upload a resume to see how an Applicant Tracking System interprets it. We highlight elements that ATS parsers struggle with.
          </p>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1 min-h-0">
          {/* Left panel: Upload and Results */}
          <div className="flex flex-col gap-6 overflow-y-auto pr-2 pb-10">
            <label className="rounded-xl border-2 border-dashed border-border p-8 text-center flex flex-col items-center justify-center bg-surface-sunken cursor-pointer hover:bg-muted/30 transition-colors">
              <UploadCloud className="w-10 h-10 mb-4 text-muted-foreground" />
              <p className="text-muted-foreground mb-4 font-mono text-sm">Drag and drop a PDF here, or click to browse</p>
              <input type="file" accept="application/pdf" className="hidden" onChange={handleFileChange} />
            </label>

            {isLoading && (
              <div className="flex items-center gap-3 p-4 bg-surface-sunken rounded-md border border-border">
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
                <span className="font-mono text-sm">Analyzing document structure...</span>
              </div>
            )}

            {result && (
              <div className="space-y-6">
                <div className="p-6 bg-surface-sunken rounded-xl border border-border">
                  <h3 className="font-heading uppercase tracking-chip text-sm text-muted-foreground mb-2">ATS Compatibility Score</h3>
                  <div className="flex items-end gap-2 mb-4">
                    <span className="text-5xl font-bold font-mono">{result.score.toFixed(1)}</span>
                    <span className="text-xl text-muted-foreground font-mono mb-1">/ 100</span>
                  </div>
                  
                  {/* Breakdown */}
                  <div className="space-y-2 mt-6">
                    {Object.entries(result.breakdown).map(([key, value]) => {
                      if (value === 0) return null;
                      return (
                        <div key={key} className="flex justify-between items-center text-sm font-mono pb-2 border-b border-border/50">
                          <span className="capitalize text-muted-foreground">{key.replace(/_/g, ' ')}</span>
                          <span className={value > 0 && key.includes('penalty') ? 'text-destructive' : 'text-primary'}>
                            {key.includes('penalty') ? '-' : '+'}{value} pts
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {result.flags.length > 0 && (
                  <div className="p-4 bg-destructive/10 text-destructive rounded-xl border border-destructive/20">
                    <h3 className="font-bold flex items-center gap-2 mb-3">
                      <AlertTriangle className="w-5 h-5" /> Severe Issues Detected
                    </h3>
                    <ul className="list-disc pl-5 space-y-2 text-sm font-mono">
                      {result.flags.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right panel: PDF Viewer */}
          <div className="md:col-span-2 bg-surface-sunken rounded-xl border border-border flex flex-col overflow-hidden min-h-[600px]">
            {file ? (
              <PdfViewer file={file} boundingBoxes={result?.boundingBoxes || []} />
            ) : (
              <div className="flex-1 flex items-center justify-center text-muted-foreground font-mono text-sm">
                PDF Preview will appear here
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
