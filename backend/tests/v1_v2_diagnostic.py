"""
V1 vs V2 Extraction Diagnostic
================================
Runs BOTH V1 (PDFPipelineV3) and V2 (StructuralParsingService + DeterministicExtractionService)
on the same 25 PDFs and compares field-by-field extraction quality.
"""
import json
import sys
import time
import os
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# V1 imports
from src.core.pipeline import PDFPipelineV3

# V2 imports
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.deterministic_extraction_service import DeterministicExtractionService

import logging
logging.basicConfig(level=logging.ERROR)


def run():
    resume_dir = Path("data/resumes")
    pdfs = sorted(resume_dir.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found!")
        return

    print(f"{'='*80}")
    print(f" V1 vs V2 EXTRACTION DIAGNOSTIC — {len(pdfs)} PDFs")
    print(f"{'='*80}")

    # Instantiate both pipelines
    v1_pipe = PDFPipelineV3()
    v2_structural = StructuralParsingService()
    v2_extraction = DeterministicExtractionService()

    # Counters
    v1_stats = {"name": 0, "email": 0, "skills": 0, "experience": 0, "education": 0, "errors": 0, "time": 0.0}
    v2_stats = {"name": 0, "email": 0, "skills": 0, "experience": 0, "education": 0, "errors": 0, "time": 0.0}

    for pdf in pdfs:
        print(f"\n{'─'*70}")
        print(f"  FILE: {pdf.name}")
        print(f"{'─'*70}")

        # ── V1 Extraction ────────────────────────────────────────────
        t0 = time.time()
        try:
            v1_result = v1_pipe.extract(str(pdf))
            v1_fields = v1_result.fields
            v1_dt = (time.time() - t0) * 1000

            v1_name = (v1_fields.get("personal_info", {}).get("name") or "").strip()
            v1_email = v1_fields.get("personal_info", {}).get("email") or ""
            v1_skills = v1_fields.get("skills", [])
            v1_exp = v1_fields.get("experience", [])
            v1_edu = v1_fields.get("education", [])

            if v1_name and v1_name != "Unknown Candidate": v1_stats["name"] += 1
            if v1_email: v1_stats["email"] += 1
            if v1_skills: v1_stats["skills"] += 1
            if v1_exp: v1_stats["experience"] += 1
            if v1_edu: v1_stats["education"] += 1
            v1_stats["time"] += v1_dt

            print(f"  V1: name='{v1_name}' | email='{v1_email}' | "
                  f"skills={len(v1_skills)} | exp={len(v1_exp)} | edu={len(v1_edu)} | {v1_dt:.0f}ms")
            if v1_skills:
                print(f"      skills_sample: {v1_skills[:8]}")
        except Exception as e:
            v1_stats["errors"] += 1
            print(f"  V1: ERROR — {e}")

        # ── V2 Extraction ────────────────────────────────────────────
        t0 = time.time()
        try:
            with open(pdf, "rb") as f:
                pdf_bytes = f.read()
            structural = v2_structural.parse(pdf_bytes, pdf.name)
            ext_res = v2_extraction.parse(structural, pdf.name)
            v2_dt = (time.time() - t0) * 1000

            v2_name = ext_res.name.value if ext_res.name else ""
            v2_email = ext_res.email.value if ext_res.email else ""
            v2_skills_val = ext_res.skills.value if ext_res.skills else []
            v2_exp_val = ext_res.experience.value if ext_res.experience else []
            v2_edu_val = ext_res.education.value if ext_res.education else []

            if v2_name: v2_stats["name"] += 1
            if v2_email: v2_stats["email"] += 1
            if v2_skills_val: v2_stats["skills"] += 1
            if v2_exp_val: v2_stats["experience"] += 1
            if v2_edu_val: v2_stats["education"] += 1
            v2_stats["time"] += v2_dt

            print(f"  V2: name='{v2_name}' | email='{v2_email}' | "
                  f"skills={len(v2_skills_val)} | exp={len(v2_exp_val)} | edu={len(v2_edu_val)} | {v2_dt:.0f}ms")
            if v2_skills_val:
                print(f"      skills_sample: {v2_skills_val[:8]}")

            # Highlight regressions
            issues = []
            if v1_name and not v2_name: issues.append("NAME_LOST")
            if v1_skills and not v2_skills_val: issues.append("SKILLS_LOST")
            if v1_exp and not v2_exp_val: issues.append("EXP_LOST")
            if v1_edu and not v2_edu_val: issues.append("EDU_LOST")
            if len(v2_skills_val) < len(v1_skills) * 0.5: issues.append(f"SKILLS_DROP({len(v1_skills)}→{len(v2_skills_val)})")
            if issues:
                print(f"  ⚠️  REGRESSIONS: {', '.join(issues)}")

            # Show unresolved chunks
            if ext_res.unresolved:
                print(f"  V2 unresolved chunks: {len(ext_res.unresolved)}")
                for uc in ext_res.unresolved[:3]:
                    print(f"      [{uc.field_name}] section='{uc.section}' text='{uc.text[:80]}...'")

        except Exception as e:
            v2_stats["errors"] += 1
            print(f"  V2: ERROR — {e}")

    # ── Summary ──────────────────────────────────────────────────
    total = len(pdfs)
    print(f"\n{'='*80}")
    print(f" SUMMARY ({total} PDFs)")
    print(f"{'='*80}")
    print(f"{'Metric':<25} {'V1':>10} {'V2':>10} {'Delta':>10}")
    print(f"{'─'*55}")
    for field in ["name", "email", "skills", "experience", "education"]:
        v1v = v1_stats[field]
        v2v = v2_stats[field]
        delta = v2v - v1v
        sign = "+" if delta > 0 else ""
        print(f"{field:<25} {v1v:>10} {v2v:>10} {sign}{delta:>9}")
    print(f"{'errors':<25} {v1_stats['errors']:>10} {v2_stats['errors']:>10}")
    print(f"{'avg ms/resume':<25} {v1_stats['time']/total:>10.1f} {v2_stats['time']/total:>10.1f}")

    # Extraction Quality (V1 formula)
    v1_s = total - v1_stats["errors"] or 1
    v2_s = total - v2_stats["errors"] or 1
    v1_eq = (0.20 * v1_stats["name"]/v1_s + 0.25 * v1_stats["skills"]/v1_s +
             0.25 * v1_stats["experience"]/v1_s + 0.20 * v1_stats["education"]/v1_s +
             0.10 * v1_stats["email"]/v1_s) * 100
    v2_eq = (0.20 * v2_stats["name"]/v2_s + 0.25 * v2_stats["skills"]/v2_s +
             0.25 * v2_stats["experience"]/v2_s + 0.20 * v2_stats["education"]/v2_s +
             0.10 * v2_stats["email"]/v2_s) * 100
    print(f"\n{'Extraction Quality':<25} {v1_eq:>9.1f}% {v2_eq:>9.1f}% {v2_eq-v1_eq:>+9.1f}%")


if __name__ == "__main__":
    run()
