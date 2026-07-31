#!/usr/bin/env python3
"""
scripts/debug_regex_failures.py
=================================
Diagnoses regex parser failures by printing out the exact text chunks
and regex patterns when a critical field is missed.
"""

import sys
import os
import fitz
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
BACKEND_DIR  = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.extractors.contact.contact_parser import ContactParser, _EMAIL_RE
from src.extractors.experience.experience_parser import ExperienceParser, DATE_RANGE_RE
from src.extractors.skills.skills_parser import SkillsParser

def extract_pymupdf_raw(pdf_path: str) -> dict:
    doc = fitz.open(pdf_path)
    pages_text = []
    hyperlinks = []
    for page in doc:
        pages_text.append(page.get_text())
        for link in page.get_links():
            if 'uri' in link:
                hyperlinks.append({"uri": link['uri']})
    return {
        "raw_text": "\n".join(pages_text),
        "hyperlinks": hyperlinks
    }

def main():
    data_dir = BACKEND_DIR / "data" / "resumes"
    pdfs = sorted(data_dir.glob("*.pdf"))

    cp = ContactParser()
    ep = ExperienceParser()
    sp = SkillsParser()

    print("=" * 80)
    print("  REGEX FAILURE DIAGNOSTIC")
    print("=" * 80)

    for pdf in pdfs:
        data = extract_pymupdf_raw(str(pdf))
        raw = data["raw_text"]
        hyperlinks = data["hyperlinks"]

        contact = cp.parse(raw_text=raw, hyperlinks=hyperlinks)
        experience = ep.parse(raw)
        skills = sp.parse(full_text=raw, also_scan_fulltext=True)

        missing = []
        if not contact.get("email"): missing.append("email")
        if not contact.get("phone"): missing.append("phone")
        if not experience: missing.append("experience")
        if not skills: missing.append("skills")

        # Skip resumes that are intentionally empty (like celebrity lists)
        # We can detect these by checking if there's any standard resume sections
        # But let's just print the first 5 real failures.
        if missing:
            print(f"\n{'━' * 80}")
            print(f"  FILE: {pdf.name}")
            print(f"  MISSING: {', '.join(missing)}")
            print(f"{'━' * 80}")
            
            if "email" in missing:
                print(f"  🔴 EMAIL FAILED")
                print(f"  Regex Used: {_EMAIL_RE.pattern}")
                print(f"  Hyperlinks passed: {[h['uri'] for h in hyperlinks]}")
            
            if "experience" in missing:
                print(f"\n  🔴 EXPERIENCE FAILED")
                print(f"  Regex Used: {DATE_RANGE_RE.pattern}")
                print(f"  First 300 chars of text: {raw[:300].replace('\n', ' ')}")
            
            # We'll just halt after finding a few to analyze
            break

if __name__ == "__main__":
    main()
