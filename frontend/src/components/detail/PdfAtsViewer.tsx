import { useState } from 'react';
import { Document, Page } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import type { BoundingBox } from '@/lib/api';
import { AtsOverlay } from './AtsOverlay';

interface PdfAtsViewerProps {
  pdfUrl: string;
  boundingBoxes: BoundingBox[];
}

export function PdfAtsViewer({ pdfUrl, boundingBoxes }: PdfAtsViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
  }

  return (
    <div className="flex flex-col items-center bg-muted/30 py-sp-4 rounded-brutal border-2 border-border mt-sp-4">
      <h3 className="font-heading text-lg uppercase tracking-chip mb-sp-4 w-full px-sp-4 text-left">
        ATS Scan View
      </h3>
      <Document
        file={pdfUrl}
        onLoadSuccess={onDocumentLoadSuccess}
        className="max-w-full"
        loading={<div className="p-sp-6 animate-pulse">Loading PDF...</div>}
        error={<div className="p-sp-6 text-red-500">Failed to load PDF. Is the URL valid?</div>}
      >
        {Array.from(new Array(numPages || 0), (_, index) => (
          <div key={`page_${index + 1}`} className="relative mb-sp-4 shadow-brutal border-2 border-border bg-white">
            <Page
              pageNumber={index + 1}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              className="max-w-full"
            />
            <AtsOverlay boxes={boundingBoxes} pageNumber={index + 1} />
          </div>
        ))}
      </Document>
    </div>
  );
}
