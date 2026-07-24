import React, { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAtsCheck } from '@/hooks/useV2Queries';
import { PdfAtsViewer } from '@/components/detail/PdfAtsViewer';
import type { AtsResult } from '@/lib/api-v2';

export function AtsCheckerPage() {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [atsResult, setAtsResult] = useState<AtsResult | null>(null);

  const atsCheckMutation = useAtsCheck();

  const handleUpload = useCallback(
    async (file: File) => {
      // Validate
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        toast.error('Only PDF files are supported.');
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        toast.error('File too large. Maximum is 10MB.');
        return;
      }

      // Create a local blob URL to render the PDF immediately
      const objectUrl = URL.createObjectURL(file);
      setPdfUrl(objectUrl);
      setAtsResult(null); // Clear previous result

      try {
        const result = await atsCheckMutation.mutateAsync(file);
        setAtsResult(result);
        toast.success('ATS check complete');
      } catch (err: unknown) {
        toast.error((err as Error).message || 'ATS check failed');
      }
    },
    [atsCheckMutation]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleUpload(e.dataTransfer.files[0]); // Only take the first file
      }
    },
    [handleUpload]
  );

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        handleUpload(e.target.files[0]);
        e.target.value = '';
      }
    },
    [handleUpload]
  );

  const isLoading = atsCheckMutation.isPending;

  return (
    <div className="flex-1 overflow-auto p-sp-6 flex flex-col gap-sp-6 h-full scrollbar-brutal">
      <div className="max-w-4xl mx-auto w-full">
        <h1 className="font-heading text-3xl uppercase tracking-brutal mb-sp-2 text-foreground">
          ATS Checker
        </h1>
        <p className="text-muted-foreground font-mono mb-sp-6">
          Upload a PDF to see how an ATS will parse and score it.
        </p>

        {/* Upload Zone */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleFileInputChange}
          disabled={isLoading}
        />

        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border-thick border-dashed p-sp-8 flex flex-col items-center justify-center gap-sp-4 transition-colors cursor-pointer mb-sp-8 ${
            isLoading
              ? 'border-border bg-surface-sunken opacity-50 cursor-not-allowed'
              : isDragging
                ? 'border-foreground bg-surface-hover'
                : 'border-border bg-surface-sunken hover:bg-surface-hover'
          }`}
        >
          <p className="text-base font-semibold uppercase tracking-chip text-center text-muted-foreground">
            {isDragging ? 'Drop PDF here' : 'Drop a PDF here or click browse'}
          </p>
          <Button
            variant="outline"
            onClick={handleBrowseClick}
            disabled={isLoading}
            className="border-thick border-border bg-secondary text-foreground uppercase tracking-brutal text-sm font-bold px-sp-4 py-sp-2 hover:bg-foreground hover:text-background transition-colors"
          >
            {isLoading ? 'Analyzing...' : 'Browse File'}
          </Button>
        </div>

        {/* Results Section */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center p-sp-10 bg-surface-sunken border-thick border-border">
            <div className="animate-spin w-8 h-8 border-4 border-foreground border-t-transparent rounded-full mb-sp-4" />
            <p className="font-mono text-muted-foreground">Analyzing PDF structure and layout...</p>
          </div>
        )}

        {atsResult && !isLoading && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-sp-6">
            {/* Left Col: Results Summary */}
            <div className="col-span-1 flex flex-col gap-sp-4">
              <div className="bg-white border-thick border-border p-sp-4 shadow-brutal">
                <h3 className="font-heading text-lg uppercase tracking-chip mb-sp-2">ATS Score</h3>
                <div className="text-5xl font-bold font-mono">
                  {Math.round(atsResult.ats_score)}
                  <span className="text-xl text-muted-foreground">/100</span>
                </div>
              </div>

              <div className="bg-white border-thick border-border p-sp-4 shadow-brutal">
                <h3 className="font-heading text-lg uppercase tracking-chip mb-sp-4">Issues Found</h3>
                {atsResult.flags.length === 0 ? (
                  <p className="text-green-600 font-mono text-sm">No issues found. Perfect!</p>
                ) : (
                  <div className="flex flex-col gap-sp-3">
                    {atsResult.flags.map((flag, idx) => (
                      <div key={idx} className="border-l-4 border-l-red-500 pl-sp-2">
                        <p className="font-bold text-sm uppercase tracking-chip text-red-600 mb-1">
                          {flag.severity} - {flag.issue}
                        </p>
                        <p className="text-sm font-mono text-foreground mb-1">{flag.message}</p>
                        {flag.fix_suggestion && (
                          <p className="text-xs font-mono text-muted-foreground">
                            <span className="font-bold">Fix: </span>{flag.fix_suggestion}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Right Col: PDF Viewer */}
            <div className="col-span-1 md:col-span-2">
              {pdfUrl && (
                <PdfAtsViewer pdfUrl={pdfUrl} boundingBoxes={atsResult.bounding_boxes} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
