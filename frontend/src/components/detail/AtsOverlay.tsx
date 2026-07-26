import type { BoundingBox } from '@/lib/api';

interface AtsOverlayProps {
  boxes: BoundingBox[];
  pageNumber: number;
}

export function AtsOverlay({ boxes, pageNumber }: AtsOverlayProps) {
  const pageBoxes = boxes.filter((b) => b.page === pageNumber);

  if (pageBoxes.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none z-10">
      {pageBoxes.map((box, idx) => {
        const width = box.x1 - box.x0;
        const height = box.y1 - box.y0;
        
        // Severity styling based on the issue type or hardcoded for now
        // A real implementation would parse the issue to determine color
        const isSevere = box.issue.includes('fatal') || box.issue.includes('reading_order');
        const borderColor = isSevere ? 'border-red-500' : 'border-yellow-500';
        const bgColor = isSevere ? 'bg-red-500/20' : 'bg-yellow-500/20';

        return (
          <div
            key={idx}
            title={box.issue}
            className={`absolute border-2 ${borderColor} ${bgColor} mix-blend-multiply`}
            style={{
              left: `${box.x0}px`,
              top: `${box.y0}px`,
              width: `${width}px`,
              height: `${height}px`,
            }}
          />
        );
      })}
    </div>
  );
}
