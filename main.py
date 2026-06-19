"""
main.py — Resume Intelligence Platform
=========================================
Minimal entry point for CLI extraction.

Usage:
  python main.py                              # defaults to data/resumes/souvik.pdf
  python main.py data/resumes/1.pdf           # specific PDF
  python main.py data/resumes/1.pdf fields    # show only fields
  python main.py data/resumes/1.pdf raw       # show only metadata
  python main.py data/resumes/1.pdf all       # show full ExtractionResult
"""

import sys
import json
from dataclasses import asdict
from pathlib import Path

# Ensure project root is on sys.path for src.* imports
PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.config.settings import DEFAULT_RESUME


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_RESUME)
    show = sys.argv[2] if len(sys.argv) > 2 else 'all'

    pipeline = PDFPipelineV3()
    result = pipeline.extract(pdf)

    if show == 'fields':
        print(json.dumps(result.fields, indent=2, ensure_ascii=False, default=str))
    elif show == 'raw':
        print(json.dumps(result.metadata, indent=2, ensure_ascii=False, default=str))
    else:
        out = asdict(result)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
