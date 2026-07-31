#!/usr/bin/env python3
"""
scripts/debug_extraction_failures.py
======================================
Diagnostic script for Phase 3 extraction debugging.

For each resume that fails to extract a key field (email, phone, experience),
prints a detailed failure report showing:
  - Raw PyMuPDF text (first 500 chars)
  - Hyperlinks found by PyMuPDF
  - Contact parser results
  - Date range regex matches
  - Experience parser results
  - LLM fallback status

Usage:
    cd backend && uv run python scripts/debug_extraction_failures.py
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import shutil
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── sys.path setup ─────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BACKEND_DIR  = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Configure logging to show Nova errors explicitly
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

import fitz

from src.extractors.contact.contact_parser import ContactParser
from src.extractors.experience.experience_parser import ExperienceParser, DATE_RANGE_RE
from src.extractors.education.education_parser import EducationParser
from src.extractors.skills.skills_parser import SkillsParser

# ── S3 mock ────────────────────────────────────────────────────────────────────
from unittest.mock import patch, MagicMock

_current_pdf_path: List[str] = [""]

def _s3_side_effect(service_name, *args, **kwargs):
    if service_name == "s3":
        mock_s3 = MagicMock()
        def fake_download(Bucket, Key, Filename, **_kw):
            shutil.copy(_current_pdf_path[0], Filename)
        mock_s3.download_file.side_effect = fake_download
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
from src.extraction.fallback.nova_service import NovaService


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic functions
# ─────────────────────────────────────────────────────────────────────────────

def extract_pymupdf_raw(pdf_path: str) -> dict:
    """Extract raw text, hyperlinks, and link-extracted emails from a PDF."""
    doc = fitz.open(pdf_path)
    pages_text = []
    all_links = []
    mailto_emails = []
    tel_phones = []

    for page in doc:
        pages_text.append(page.get_text())
        links = page.get_links()
        for link in links:
            uri = link.get("uri", "")
            if uri:
                all_links.append(uri)
                if uri.startswith("mailto:"):
                    mailto_emails.append(uri.replace("mailto:", "").split("?")[0])
                elif uri.startswith("tel:"):
                    tel_phones.append(uri.replace("tel:", ""))

    raw_text = "\n".join(pages_text)
    return {
        "raw_text": raw_text,
        "raw_text_first_500": raw_text[:500],
        "total_chars": len(raw_text),
        "all_links": all_links,
        "mailto_emails": mailto_emails,
        "tel_phones": tel_phones,
        "page_count": len(pages_text),
    }


def run_contact_parser(raw_text: str, links: list) -> dict:
    """Run ContactParser with both raw_text and hyperlinks."""
    cp = ContactParser()
    # Method 1: raw_text only (what V2 currently does)
    result_text_only = cp.parse(raw_text=raw_text)

    # Method 2: raw_text + hyperlink URIs appended
    link_text = "\n".join(links)
    combined = raw_text + "\n" + link_text
    result_with_links = cp.parse(raw_text=combined)

    # Method 3: using the hyperlinks parameter
    hyperlink_dicts = [{"uri": u} for u in links]
    result_with_hyperlinks_param = cp.parse(raw_text=raw_text, hyperlinks=hyperlink_dicts)

    return {
        "text_only": {
            "name": result_text_only.get("name"),
            "email": result_text_only.get("email"),
            "phone": result_text_only.get("phone"),
        },
        "with_links_appended": {
            "name": result_with_links.get("name"),
            "email": result_with_links.get("email"),
            "phone": result_with_links.get("phone"),
        },
        "with_hyperlinks_param": {
            "name": result_with_hyperlinks_param.get("name"),
            "email": result_with_hyperlinks_param.get("email"),
            "phone": result_with_hyperlinks_param.get("phone"),
        },
    }


def run_date_regex(raw_text: str) -> list:
    """Find all date range matches in text."""
    matches = []
    for m in DATE_RANGE_RE.finditer(raw_text):
        matches.append({
            "full_match": m.group(0),
            "start": m.group("start"),
            "end": m.group("end"),
            "span": m.span(),
        })
    return matches


def test_nova_direct(text_chunk: str) -> dict:
    """Test a direct Nova invocation and capture the exact error."""
    nova = NovaService()
    result = {"status": "unknown", "error": None, "response": None}

    try:
        import boto3
        from botocore.config import Config

        config = Config(
            connect_timeout=10,
            read_timeout=10,
            retries={"max_attempts": 0},  # No retries — we want the raw error
        )
        from src.config.aws import get_settings
        s = get_settings()
        client = boto3.client(
            "bedrock-runtime",
            region_name=s.aws_default_region,
            aws_access_key_id=s.aws_access_key_id,
            aws_secret_access_key=s.aws_secret_access_key,
            config=config,
        )

        response = client.converse(
            modelId="amazon.nova-micro-v1:0",
            system=[{"text": "You are a test. Respond with: {\"status\": \"ok\"}"}],
            messages=[
                {"role": "user", "content": [{"text": "Test ping"}]},
            ],
            inferenceConfig={"temperature": 0.0, "maxTokens": 50},
        )

        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        raw_text = ""
        for block in content_blocks:
            if isinstance(block, dict) and "text" in block:
                raw_text = block["text"]
                break

        result["status"] = "SUCCESS"
        result["response"] = raw_text
        result["http_status"] = response.get("ResponseMetadata", {}).get("HTTPStatusCode")

    except Exception as exc:
        exc_type = type(exc).__name__
        result["status"] = f"FAILED ({exc_type})"
        result["error"] = str(exc)
        # Try to extract HTTP status from the exception
        if hasattr(exc, "response"):
            result["http_status"] = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            result["error_code"] = exc.response.get("Error", {}).get("Code")
            result["error_message"] = exc.response.get("Error", {}).get("Message")

    return result


def run_full_pipeline(pdf_path: str) -> dict:
    """Run the full V2 extraction pipeline on a single resume."""
    pipeline = ExtractionPipeline()
    doc_id = f"debug-{uuid.uuid4().hex[:8]}"
    _current_pdf_path[0] = pdf_path

    result = pipeline.run_pipeline(
        pdf_path=pdf_path,
        doc_id=doc_id,
        s3_bucket="debug-bucket",
        s3_key=f"debug/{doc_id}.pdf",
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    data_dir = BACKEND_DIR / "data" / "resumes"
    if not data_dir.exists():
        print(f"ERROR: Resume directory not found: {data_dir}")
        sys.exit(1)

    pdfs = sorted(data_dir.glob("*.pdf"))
    if not pdfs:
        print("ERROR: No PDFs found")
        sys.exit(1)

    print("=" * 80)
    print("  PHASE 3 EXTRACTION FAILURE DIAGNOSTIC REPORT")
    print("=" * 80)

    # ── Step 1: Test Nova LLM directly ────────────────────────────────────────
    print("\n" + "─" * 80)
    print("  ISSUE 1: BEDROCK LLM FALLBACK STATUS")
    print("─" * 80)

    nova_result = test_nova_direct("Test ping")
    print(f"  Nova Status:      {nova_result['status']}")
    if nova_result.get("http_status"):
        print(f"  HTTP Status Code: {nova_result['http_status']}")
    if nova_result.get("error_code"):
        print(f"  AWS Error Code:   {nova_result['error_code']}")
    if nova_result.get("error_message"):
        print(f"  AWS Error Msg:    {nova_result['error_message']}")
    if nova_result.get("error"):
        print(f"  Full Error:       {nova_result['error']}")
    if nova_result.get("response"):
        print(f"  Response:         {nova_result['response'][:200]}")

    # ── Step 2: Find failed resumes ───────────────────────────────────────────
    print("\n" + "─" * 80)
    print("  SCANNING ALL 50 RESUMES FOR EXTRACTION FAILURES...")
    print("─" * 80)

    cp = ContactParser()
    ep = ExperienceParser()
    failures = []

    import multiprocessing

    for pdf in pdfs:
        print(f"Processing {pdf.name}...", flush=True)
        pymupdf_data = extract_pymupdf_raw(str(pdf))
        raw = pymupdf_data["raw_text"]
        link_text = "\n".join(pymupdf_data["all_links"])
        combined = raw + "\n" + link_text
        
        contact = cp.parse(raw_text=combined)
        experience = ep.parse(raw)

        missing = []
        if not contact.get("email"):
            missing.append("email")
        if not contact.get("phone"):
            missing.append("phone")
        if not experience:
            missing.append("experience")

        if missing:
            failures.append({
                "pdf": pdf,
                "missing": missing,
                "pymupdf_data": pymupdf_data,
            })

    print(f"  Total resumes:    {len(pdfs)}")
    print(f"  With failures:    {len(failures)}")

    email_missing = sum(1 for f in failures if "email" in f["missing"])
    phone_missing = sum(1 for f in failures if "phone" in f["missing"])
    exp_missing = sum(1 for f in failures if "experience" in f["missing"])
    print(f"  Missing email:    {email_missing}")
    print(f"  Missing phone:    {phone_missing}")
    print(f"  Missing exp:      {exp_missing}")

    # ── Step 3: Detailed diagnostic for worst 5 ──────────────────────────────
    # Prioritize resumes missing the most fields
    failures.sort(key=lambda f: len(f["missing"]), reverse=True)

    print("\n" + "=" * 80)
    print("  DETAILED FAILURE DIAGNOSTICS (top 5 worst)")
    print("=" * 80)

    for i, fail in enumerate(failures[:5]):
        pdf = fail["pdf"]
        data = fail["pymupdf_data"]

        print(f"\n{'━' * 80}")
        print(f"  RESUME #{i+1}: {pdf.name}")
        print(f"  Missing Fields: {', '.join(fail['missing'])}")
        print(f"{'━' * 80}")

        # Raw text preview
        print(f"\n  ── Raw PyMuPDF Text (first 500 chars) ──")
        preview = data["raw_text_first_500"].replace("\n", "\n    ")
        print(f"    {preview}")

        # Hyperlinks
        print(f"\n  ── Hyperlinks Found ({len(data['all_links'])} total) ──")
        if data["all_links"]:
            for link in data["all_links"][:10]:
                print(f"    • {link}")
        else:
            print("    (none)")

        print(f"  ── mailto: emails: {data['mailto_emails'] or '(none)'}")
        print(f"  ── tel: phones:    {data['tel_phones'] or '(none)'}")

        # Contact parser comparison
        print(f"\n  ── Contact Parser Results ──")
        contact_results = run_contact_parser(data["raw_text"], data["all_links"])
        for method, result in contact_results.items():
            emoji = "✅" if result.get("email") or result.get("phone") else "❌"
            print(f"    {emoji} {method:30s} → email={result.get('email')}, phone={result.get('phone')}, name={result.get('name')}")

        # Date ranges
        print(f"\n  ── Date Range Regex Matches ──")
        date_matches = run_date_regex(data["raw_text"])
        if date_matches:
            for dm in date_matches[:8]:
                print(f"    • {dm['full_match']}")
        else:
            print("    (none found — experience parser will return empty)")

        # Experience parser
        print(f"\n  ── Experience Parser Results ──")
        experience = ExperienceParser().parse(data["raw_text"])
        if experience:
            for exp in experience[:3]:
                role = exp.get("role", "?")
                company = exp.get("company", "?")
                start = exp.get("start", "?")
                end = exp.get("end", "?")
                print(f"    • {role} @ {company} ({start} – {end})")
        else:
            print("    (none extracted)")

        # LLM status
        print(f"\n  ── LLM Fallback Status ──")
        print(f"    Nova status: {nova_result['status']}")
        if nova_result["status"].startswith("FAILED"):
            print(f"    → LLM cannot fill gaps for this resume")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  ROOT CAUSE SUMMARY")
    print("=" * 80)

    if nova_result["status"].startswith("FAILED"):
        print(f"""
  🔴 ISSUE 1: LLM FALLBACK IS DEAD
     Error: {nova_result.get('error_code', 'Unknown')} — {nova_result.get('error_message', nova_result.get('error', 'Unknown'))}
     Impact: Nova cannot fill ANY null fields from deterministic parsing.
     Fix: Either wait for quota reset, upgrade AWS plan, or switch to a different model.
""")
    else:
        print(f"""
  🟢 ISSUE 1: LLM FALLBACK IS WORKING
     Response: {nova_result.get('response', 'N/A')[:100]}
""")

    if email_missing > 0:
        print(f"""  🟡 ISSUE 2: EMAIL EXTRACTION GAPS ({email_missing}/{len(pdfs)} missing)
     Resumes with mailto: links but no email extracted: check if hyperlinks
     are being passed to ContactParser via the 'hyperlinks' param.
""")

    if exp_missing > 0:
        print(f"""  🔴 ISSUE 3: EXPERIENCE EXTRACTION GAPS ({exp_missing}/{len(pdfs)} missing)
     The ExperienceParser relies on DATE_RANGE_RE as its anchor.
     Resumes without standard date formats (e.g., "2 years", "Summer 2020",
     or tabular layouts) produce zero matches.
     The V2 MarkdownExtractionService does NOT run section detection or
     multiple fallback strategies like V1's PDFPipelineV3 does.
""")

    print("=" * 80)


if __name__ == "__main__":
    main()
