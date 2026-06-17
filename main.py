"""
main.py — Resume Extraction Pipeline v3
=========================================
Usage:
  python main.py                          # defaults to resume/souvik.pdf
  python main.py resume/1.pdf             # specific PDF
  python main.py resume/1.pdf fields      # show only fields
  python main.py resume/1.pdf raw         # show only metadata
  python main.py resume/1.pdf all         # show full ExtractionResult
"""

import sys
import json
from dataclasses import asdict
from pipeline import PDFPipelineV3


def main():
    pdf  = sys.argv[1] if len(sys.argv) > 1 else 'resume/souvik.pdf'
    show = sys.argv[2] if len(sys.argv) > 2 else 'all'

    pipeline = PDFPipelineV3()
    result   = pipeline.extract(pdf)

    if show == 'fields':
        print(json.dumps(result.fields, indent=2, ensure_ascii=False, default=str))
    elif show == 'raw':
        print(json.dumps(result.metadata, indent=2, ensure_ascii=False, default=str))
    else:
        out = asdict(result)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
