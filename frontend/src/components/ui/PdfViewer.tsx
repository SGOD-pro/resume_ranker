import { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { Loader2 } from 'lucide-react';

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export interface BoundingBox {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  severity: 'warning' | 'severe';
  reason: string;
}

interface PdfViewerProps {
  url?: string;
  file?: File;
  boundingBoxes?: BoundingBox[];
}

export function PdfViewer({ url, file, boundingBoxes = [] }: PdfViewerProps) {
  const [numPages, setNumPages] = useState<number>();
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [scale, setScale] = useState(1.0);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
  }

  const renderBoundingBoxes = (pageIndex: number) => {
    // react-pdf coordinates match standard PDF points
    const boxesForPage = boundingBoxes.filter(b => b.page === pageIndex + 1);
    
    return boxesForPage.map((box, i) => (
      <div
        key={i}
        title={box.reason}
        className={`absolute border-2 bg-opacity-20 pointer-events-none z-50 ${
          box.severity === 'severe' 
            ? 'border-red-500 bg-red-500' 
            : 'border-yellow-500 bg-yellow-500'
        }`}
        style={{
          left: `${box.x0 * scale}px`,
          top: `${box.y0 * scale}px`,
          width: `${(box.x1 - box.x0) * scale}px`,
          height: `${(box.y1 - box.y0) * scale}px`,
        }}
      />
    ));
  };

  return (
    <div className="flex flex-col bg-muted/20 p-4 rounded-md overflow-auto relative min-h-[600px] w-full border border-border">
      {/* Toolbar */}
      <div className="sticky top-0 left-0 right-0 z-10 flex gap-4 items-center justify-center bg-background/90 p-2 backdrop-blur border border-border rounded-md shadow-sm mb-4 mx-auto w-fit">
        <button 
          onClick={() => setPageNumber(p => Math.max(1, p - 1))}
          disabled={pageNumber <= 1}
          className="px-2 py-1 bg-surface-sunken rounded text-sm disabled:opacity-50"
        >
          Prev
        </button>
        <span className="text-sm font-mono">
          {pageNumber} / {numPages || '?'}
        </span>
        <button 
          onClick={() => setPageNumber(p => Math.min(numPages || p, p + 1))}
          disabled={pageNumber >= (numPages || 1)}
          className="px-2 py-1 bg-surface-sunken rounded text-sm disabled:opacity-50"
        >
          Next
        </button>
        
        <div className="w-px h-4 bg-border mx-2" />
        
        <button onClick={() => setScale(s => s - 0.2)} className="px-2 py-1 bg-surface-sunken rounded text-sm">-</button>
        <span className="text-sm font-mono">{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale(s => s + 0.2)} className="px-2 py-1 bg-surface-sunken rounded text-sm">+</button>
      </div>

      <div className="mx-auto w-fit">
        <Document
          file={file || url}
          onLoadSuccess={onDocumentLoadSuccess}
          loading={<Loader2 className="animate-spin w-8 h-8 text-muted-foreground mt-20" />}
          error={<div className="text-destructive p-4">Failed to load PDF. Please make sure the URL is accessible.</div>}
        >
          <div className="relative shadow-md border border-border bg-white">
            <Page 
              pageNumber={pageNumber} 
              scale={scale} 
              renderTextLayer={true}
              renderAnnotationLayer={true}
              className="max-w-full"
              loading={<div className="w-[600px] h-[800px] flex items-center justify-center bg-white" />}
            />
            {renderBoundingBoxes(pageNumber - 1)}
          </div>
        </Document>
      </div>
    </div>
  );
}
