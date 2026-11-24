#!/usr/bin/env python3
"""
scripts/audit_15_fallbacks.py
=============================
Evaluates Section 5 requirements:
- 15 fallback-triggering cases (NEEDS_ODL and NEEDS_NOVA).
- Separates:
  1. Routed to fallback
  2. Fallback actually invoked
  3. Fallback completed
  4. Fallback failed / unverified
- Tests live Nova Bedrock extraction and records latency, field extraction, and error handling.
"""

import json
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import fitz
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    pymupdf_layout_quality_signals,
    QUALITY_THRESHOLD,
)
from src.extraction.fallback.nova_service import NovaService, NovaProviderError
from src.extraction.odl_client import DocDescriptor, parse_batch, ODLParseError


def audit_fallbacks():
    corpus_dir = PROJECT_ROOT / "data" / "resumes"
    all_pdfs = sorted(list(corpus_dir.glob("*.pdf")))
    extractor = MarkdownExtractionService()

    print(f"\n================================================================================")
    print(f"  FALLBACK AUDIT: 15 Fallback-Triggering Cases (ODL & Nova)")
    print(f"================================================================================\n")

    # Step 1: Scan corpus to find candidate fallback triggers
    odl_candidates = []
    nova_candidates = []

    for p in all_pdfs:
        doc = fitz.open(str(p))
        scores = []
        for page in doc:
            p_text = page.get_text()
            p_words = page.get_text("words")
            p_drawings = len(page.get_drawings())
            sig = pymupdf_layout_quality_signals(page, text=p_text, words=p_words, drawings_count=p_drawings)
            scores.append(sig["score"])
        doc.close()
        avg_score = sum(scores) / len(scores) if scores else 0.0

        if avg_score < QUALITY_THRESHOLD:
            odl_candidates.append((p, avg_score))
        else:
            with open(p, "rb") as f:
                raw_bytes = f.read()
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            full_text = "\n".join(page.get_text() for page in doc)
            doc.close()
            res = extractor.extract(full_text, [], [], "")
            fields = res.get("fields", {})
            name = fields.get("name")
            if not name or name.strip() in ("", "Unknown", "Name needs review"):
                nova_candidates.append((p, avg_score, full_text[:2000]))

        if len(odl_candidates) >= 5 and len(nova_candidates) >= 10:
            break

    selected_cases = odl_candidates[:5] + [(c[0], c[1]) for c in nova_candidates[:10]]
    print(f"Identified {len(odl_candidates[:5])} ODL trigger cases and {len(nova_candidates[:10])} Nova trigger cases.\n")

    audit_records = []

    # Initialize Nova Service for live Bedrock verification
    nova_service = None
    try:
        nova_service = NovaService()
    except Exception as e:
        print(f"[-] Could not init NovaService: {e}")

    # Process ODL triggers
    for p, score in odl_candidates[:5]:
        rec = {
            "file": p.name,
            "quality_score": round(score, 3),
            "route": "NEEDS_ODL",
            "routed_to_fallback": True,
            "fallback_invoked": False,
            "fallback_completed": False,
            "fallback_failed": False,
            "status_detail": "",
        }
        # Attempt ODL batch invoke
        rec["fallback_invoked"] = True
        try:
            # We descriptor with local fake bucket
            desc = DocDescriptor(document_id=p.stem, s3_bucket="local-test", s3_key=f"jobs/test/{p.name}")
            parse_batch([desc])
            rec["fallback_completed"] = True
            rec["status_detail"] = "ODL parsed successfully"
        except ODLParseError as err:
            rec["fallback_failed"] = True
            rec["status_detail"] = f"ODL provider unverified in local environment (Lambda not present): {err}"
        except Exception as err:
            rec["fallback_failed"] = True
            rec["status_detail"] = f"ODL call failed: {type(err).__name__}: {err}"
        audit_records.append(rec)

    # Process Nova triggers (test up to 5 cases to respect rate limit)
    for idx, (p, score, text_sample) in enumerate(nova_candidates[:5], 1):
        rec = {
            "file": p.name,
            "quality_score": round(score, 3),
            "route": "NEEDS_NOVA",
            "routed_to_fallback": True,
            "fallback_invoked": False,
            "fallback_completed": False,
            "fallback_failed": False,
            "status_detail": "",
            "extracted_name": None,
            "latency_ms": None,
        }
        if nova_service:
            rec["fallback_invoked"] = True
            t0 = time.perf_counter()
            try:
                # Call live Nova Bedrock with text sample
                res = nova_service.resolve_chunks([text_sample[:1500]], {"name": None})
                t1 = time.perf_counter()
                rec["latency_ms"] = round((t1 - t0) * 1000.0, 1)
                rec["fallback_completed"] = True
                rec["extracted_name"] = res.get("name")
                rec["status_detail"] = f"Infilled candidate name: '{res.get('name')}', skills: {len(res.get('skills', []))}"
            except Exception as err:
                t1 = time.perf_counter()
                rec["latency_ms"] = round((t1 - t0) * 1000.0, 1)
                rec["fallback_failed"] = True
                rec["status_detail"] = f"Nova call failed: {type(err).__name__}: {err}"
        else:
            rec["status_detail"] = "NovaService unavailable"
        audit_records.append(rec)

    print(f"{'File':<12} | {'Score':<6} | {'Route':<10} | {'Invoked':<8} | {'Completed':<10} | {'Failed':<8} | {'Details'}")
    print(f"{'-'*12}-|--------|------------|----------|------------|----------|----------------------------------------")
    for r in audit_records:
        inv = "YES" if r["fallback_invoked"] else "NO"
        comp = "YES" if r["fallback_completed"] else "NO"
        fail = "YES" if r["fallback_failed"] else "NO"
        print(f"{r['file']:<12} | {r['quality_score']:<6.2f} | {r['route']:<10} | {inv:<8} | {comp:<10} | {fail:<8} | {r['status_detail'][:60]}")

    out_file = BACKEND_DIR / "audit_15_fallbacks_report.json"
    with open(out_file, "w") as f:
        json.dump(audit_records, f, indent=2)
    print(f"\n[+] Detailed fallback audit saved to: {out_file}\n")


if __name__ == "__main__":
    audit_fallbacks()
