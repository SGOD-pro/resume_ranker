import os
import sys
from pathlib import Path
import fitz

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.extraction.structural_parsing_service import (
    pymupdf_layout_quality_signals,
    QUALITY_THRESHOLD
)

def main():
    data_dir = Path(project_root) / "data" / "resumes"
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return

    pdf_files = sorted(data_dir.glob("*.pdf"))
    import random
    random.seed(42)
    random.shuffle(pdf_files)
    pdf_files = pdf_files[:200]
    
    print(f"Found {len(pdf_files)} PDFs in {data_dir.name} (seed=42)")

    false_negatives = []
    
    for pdf_path in pdf_files:
        try:
            doc = fitz.open(pdf_path)
            page_scores = []
            
            for page in doc:
                signals = pymupdf_layout_quality_signals(page)
                page_scores.append(signals["score"])
                
            if not page_scores:
                continue
                
            avg_score = sum(page_scores) / len(page_scores)
            min_score = min(page_scores)
            
            # Print if avg score passed (>= 0.70) BUT it contained a severely penalised page (min_score < 0.60)
            if avg_score >= QUALITY_THRESHOLD and min_score < 0.60:
                false_negatives.append({
                    "file": pdf_path.name,
                    "avg_score": round(avg_score, 3),
                    "min_score": round(min_score, 3),
                    "details": [
                        pymupdf_layout_quality_signals(page) for page in fitz.open(pdf_path)
                    ]
                })
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}")

    print("\n" + "="*50)
    print(f"FALSE NEGATIVES: {len(false_negatives)}")
    print("="*50)
    print("These passed the composite quality gate (avg_score >= 0.70) BUT have a page with score < 0.60 (e.g. 2-column page).\n")
    
    for fn in false_negatives[:10]: # Print top 10
        print(f"File: {fn['file']}")
        print(f"  Avg Score: {fn['avg_score']} (Threshold: {QUALITY_THRESHOLD})")
        print(f"  Min Page Score: {fn['min_score']}")
        print("  Page Breakdown:")
        for i, page_detail in enumerate(fn['details']):
            print(f"    Page {i+1}: Score={page_detail['score']}, RO={page_detail['reading_order']}, "
                  f"ColPenalty={page_detail['col_penalty']}, CharDen={page_detail['char_density']}, "
                  f"Table={page_detail['not_table_heavy']}, N_Cols={page_detail['n_x_clusters']}")
        print("-" * 30)

if __name__ == "__main__":
    main()
