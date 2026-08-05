#!/usr/bin/env python3
"""
scripts/debug_experience_failures.py
=====================================
Runs the structural + regex pipeline on up to 100 resumes and halts on each
resume where experience is empty.  Prints:
  - File name and parse path (PyMuPDF or ODL)
  - The raw text of the "Experience" section if the section router found it
  - All ODL elements whose content contains year-like strings (date candidates)
  - First 1000 chars of the document otherwise

Hypotheses under investigation:
  H1: Dates formatted as YYYY.MM (e.g. 2020.08 - 2021.08)
  H2: End date uses mixed-case text "Current" or "Now" (not kerned)
  H3: ODL heading content includes ## prefix -> section router fails match

Usage:
    cd backend && uv run python scripts/debug_experience_failures.py
"""
from __future__ import annotations

import os
import re
import sys
import uuid
import shutil
import random
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPT_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── S3 mock (local-only) ───────────────────────────────────────────────────────
_current_pdf_path: list = [""]

def _s3_side_effect(service_name, *args, **kwargs):
    if service_name == "s3":
        mock_s3 = MagicMock()
        def fake_download(Bucket, Key, Filename, **_kw):
            shutil.copy(_current_pdf_path[0], Filename)
        mock_s3.download_file.side_effect = fake_download
        mock_s3.upload_file = MagicMock()
        return mock_s3
    _s3_patch.stop()
    try:
        import boto3 as _boto3
        client = _boto3.client(service_name, *args, **kwargs)
    finally:
        _s3_patch.start()
    return client

_s3_patch = patch("boto3.client", side_effect=_s3_side_effect)
_s3_patch.start()

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.config.aws import get_settings

# ── Section-finder regex (mirrors section registry keywords) ───────────────────
_EXP_HEADING_RE = re.compile(
    r'^#+\s*(?:work\s+)?(?:professional\s+)?(?:experience|employment(?:\s+history)?|'
    r'career\s+history|work\s+history|work\s+experience)',
    re.I | re.MULTILINE,
)
_NEXT_HEADING_RE = re.compile(r'^#+\s+\S', re.MULTILINE)

# Date-candidate: anything that looks like it could be a year/date range
_DATE_CANDIDATE_RE = re.compile(
    r'\b(?:19|20)\d{2}\b'
    r'|\b\d{1,2}[./]\d{4}\b'
    r'|\b\d{4}[./]\d{1,2}\b'
    r'|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}'
    r'|present|current|now|till\s+date',
    re.I,
)


def _extract_experience_section(text: str):
    m = _EXP_HEADING_RE.search(text)
    if not m:
        return None
    start = m.end()
    rest = text[start:]
    nm = _NEXT_HEADING_RE.search(rest)
    end = nm.start() if nm else len(rest)
    section = rest[:end].strip()
    return section if section else None


def _element_date_candidates(elements: list) -> list:
    hits = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        c = str(el.get("content", ""))
        if _DATE_CANDIDATE_RE.search(c):
            hits.append({
                "type":    el.get("type", "?"),
                "page":    el.get("page number", "?"),
                "bbox":    el.get("bounding_box", "?"),
                "content": c[:200],
            })
    return hits


def run_diagnostic(max_pdfs: int = 100, max_failures: int = 10) -> None:
    settings = get_settings()
    pipeline = ExtractionPipeline()

    resume_dir = BACKEND_DIR / "data" / "resumes"
    pdf_files = sorted(resume_dir.glob("*.pdf"))
    if not pdf_files:
        print("No PDFs found in data/resumes/")
        return

    random.seed(42)
    sample = random.sample(pdf_files, min(max_pdfs, len(pdf_files)))
    print(f"Scanning {len(sample)} resumes for experience failures ...")

    failures = 0
    for pdf_path in sample:
        _current_pdf_path[0] = str(pdf_path)
        doc_id = str(uuid.uuid4())

        try:
            parse_result = pipeline.structural_service.parse_pdf(
                str(pdf_path), doc_id, settings.s3_bucket_name, "dummy-key"
            )
            md_result = pipeline.markdown_service.extract(
                parse_result.markdown,
                parse_result.hyperlinks,
                parse_result.elements,
            )
            fields = md_result["fields"]
            experience = fields.get("experience") or []

            if experience:
                continue

            failures += 1
            parse_path = "ODL" if parse_result.quality_score < 0.9 else "PyMuPDF"

            print("=" * 90)
            print(f"FAILURE #{failures}: {pdf_path.name}  [{parse_path}]")
            print("=" * 90)

            exp_section = _extract_experience_section(parse_result.markdown)
            if exp_section:
                print("\n-- [A] EXPERIENCE SECTION (from Markdown heading search) --")
                print(exp_section[:1500])
            else:
                print("\n-- [A] No ## Experience heading found in Markdown --")
                print("First 1000 chars of document:")
                print(parse_result.markdown[:1000])

            if parse_result.elements:
                date_elems = _element_date_candidates(parse_result.elements)
                print(f"\n-- [B] ODL elements with date-like content ({len(date_elems)} found) --")
                for i, de in enumerate(date_elems[:15]):
                    print(f"  [{i+1}] type={de['type']}  page={de['page']}  bbox={de['bbox']}")
                    print(f"       content: {de['content']!r}")

                heading_elems = [
                    el for el in parse_result.elements
                    if isinstance(el, dict) and (
                        el.get("type") == "heading"
                        or str(el.get("pdfua_tag", "")).startswith("H")
                    )
                ]
                print(f"\n-- [C] All ODL heading elements ({len(heading_elems)} found) --")
                for he in heading_elems[:20]:
                    print(f"  type={he.get('type')}  tag={he.get('pdfua_tag','?')}  "
                          f"content={str(he.get('content',''))[:100]!r}")
            else:
                print("\n-- [B] No ODL elements available (PyMuPDF path) --")

            print()

            if failures >= max_failures:
                print(f"Reached {max_failures} failures -- stopping.")
                break

        except Exception as exc:
            print(f"ERROR on {pdf_path.name}: {exc}")

    print(f"\n{'='*90}")
    print(f"Total failures: {failures} / {len(sample)} scanned")


if __name__ == "__main__":
    run_diagnostic()
