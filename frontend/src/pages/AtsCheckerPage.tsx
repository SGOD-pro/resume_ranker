import { useState } from 'react';
import { PdfViewer } from '@/components/ui/PdfViewer';
import { Loader2, UploadCloud, AlertTriangle, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';
import { checkAts } from '@/lib/api';
import type { AtsCheckResponse } from '@/store/types';

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

    try {
      const data = await checkAts(selected);
      setResult(data);
      toast.success('ATS parseability check completed.');
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'An error occurred during ATS checking.';
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 flex flex-col">
      <div className="mx-auto max-w-7xl w-full flex-1 flex flex-col">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight mb-2">B2B ATS Health Check</h1>
          <p className="text-muted-foreground">
            Upload a resume to run a deep-dive parser health check. Analyzes layout, fonts, section standardisation, and extraction fidelity.
          </p>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 flex-1 min-h-0">
          {/* Left panel: Upload and Results */}
          <div className="lg:col-span-2 flex flex-col gap-6 overflow-y-auto pr-2 pb-10">
            <label className="rounded-xl border-2 border-dashed border-border p-8 text-center flex flex-col items-center justify-center bg-surface-sunken cursor-pointer hover:bg-muted/30 transition-colors">
              <UploadCloud className="w-10 h-10 mb-4 text-muted-foreground" />
              <p className="text-muted-foreground mb-4 font-mono text-sm">Drag and drop a PDF here, or click to browse</p>
              <input type="file" accept="application/pdf" className="hidden" onChange={handleFileChange} />
            </label>

            {isLoading && (
              <div className="flex items-center gap-3 p-4 bg-surface-sunken rounded-md border border-border">
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
                <span className="font-mono text-sm">Running extraction pipeline...</span>
              </div>
            )}

            {result && (
              <div className="space-y-6">
                <div className="p-6 bg-surface-sunken rounded-xl border border-border">
                  <h3 className="font-heading uppercase tracking-chip text-sm text-muted-foreground mb-2">Parseability Score</h3>
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

                {/* Section Detection */}
                <div className="p-4 bg-surface-sunken rounded-xl border border-border">
                  <h3 className="font-bold mb-3 font-mono text-sm uppercase text-muted-foreground">Section Detection</h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-bold text-primary mb-1">FOUND:</p>
                      <div className="flex flex-wrap gap-2">
                        {(result.section_detection?.found || []).length > 0 ? result.section_detection.found.map((s, i) => (
                          <span key={i} className="px-2 py-1 bg-primary/10 text-primary text-xs rounded-md border border-primary/20">{s}</span>
                        )) : <span className="text-xs text-muted-foreground">None</span>}
                      </div>
                    </div>
                    {(result.section_detection?.missed || []).length > 0 ? (
                      <div>
                        <p className="text-xs font-bold text-destructive mb-1">MISSED (High Risk):</p>
                        <div className="flex flex-wrap gap-2">
                          {result.section_detection.missed.map((s, i) => (
                            <span key={i} className="px-2 py-1 bg-destructive/10 text-destructive text-xs rounded-md border border-destructive/20">{s}</span>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">✓ No missed sections</p>
                    )}
                  </div>
                </div>

                {/* Additional Health Checks */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-surface-sunken rounded-xl border border-border">
                    <h3 className="font-bold mb-2 text-sm">Contact Info</h3>
                    <div className="flex flex-col gap-1 text-sm font-mono">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Email:</span>
                        <span className={result.contact_info_visibility?.email ? "text-primary" : "text-destructive"}>
                          {result.contact_info_visibility?.email ? 'Found' : 'Missing/Image'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Phone:</span>
                        <span className={result.contact_info_visibility?.phone ? "text-primary" : "text-destructive"}>
                          {result.contact_info_visibility?.phone ? 'Found' : 'Missing/Image'}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="p-4 bg-surface-sunken rounded-xl border border-border">
                    <h3 className="font-bold mb-2 text-sm">Font Encoding</h3>
                    <p className={`text-sm font-mono ${(result.font_health || '').includes('Garbled') ? 'text-destructive' : 'text-primary'}`}>
                      {result.font_health}
                    </p>
                  </div>
                </div>

                <div className="p-4 bg-surface-sunken rounded-xl border border-border">
                  <h3 className="font-bold mb-2 text-sm">Date Chronology</h3>
                  <p className="text-sm font-mono text-muted-foreground">
                    {result.date_consistency}
                  </p>
                </div>

                {result.layout_flags && result.layout_flags.length > 0 && (
                  <div className="p-4 bg-destructive/10 text-destructive rounded-xl border border-destructive/20">
                    <h3 className="font-bold flex items-center gap-2 mb-3">
                      <AlertTriangle className="w-5 h-5" /> Layout Risks
                    </h3>
                    <ul className="list-disc pl-5 space-y-2 text-sm font-mono">
                      {result.layout_flags.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Keyword Preview */}
                <div className="p-4 bg-surface-sunken rounded-xl border border-border">
                  <h3 className="font-bold mb-2 text-sm">Skill / Keyword Extraction Preview</h3>
                  <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
                    This is what the parser successfully lifted from the document into structured data.
                  </p>
                  <div className="flex flex-wrap gap-2 max-h-[150px] overflow-y-auto">
                    {(result.keyword_preview || []).length > 0 ? result.keyword_preview.map((k, i) => (
                      <span key={i} className="px-2 py-1 bg-muted/50 text-foreground text-xs rounded border border-border">{k}</span>
                    )) : (
                      <span className="text-sm text-muted-foreground italic">No skills extracted.</span>
                    )}
                  </div>
                </div>

                {/* Transparent Limitations & Privacy Notice */}
                <div className="p-4 bg-muted/30 rounded-xl border border-border text-xs space-y-2">
                  <div className="flex items-center gap-2 font-bold text-muted-foreground">
                    <ShieldAlert className="w-4 h-4 text-primary" />
                    <span>ATS Health Check Transparency Policy</span>
                  </div>
                  <p className="text-muted-foreground leading-relaxed">
                    {result.limitations_disclaimer || "Informational parser diagnostic only. Passing this test does not guarantee ATS compatibility or hiring outcomes."}
                  </p>
                  <p className="text-muted-foreground/80 text-[11px] leading-relaxed">
                    Privacy notice: Uploaded resumes for this health check are retained only for ephemeral analysis and automatically purged. No profile data is shared or sold.
                  </p>
                </div>

              </div>
            )}
          </div>

          {/* Right panel: PDF Viewer */}
          <div className="lg:col-span-3 bg-surface-sunken rounded-xl border border-border flex flex-col overflow-hidden min-h-[700px]">
            {file ? (
              <PdfViewer file={file} boundingBoxes={result?.bounding_boxes || []} />
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
