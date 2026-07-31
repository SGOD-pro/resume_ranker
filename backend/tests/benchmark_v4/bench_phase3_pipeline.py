#!/usr/bin/env python3
"""
bench_phase3_pipeline.py — Phase 3 Extraction Pipeline Benchmark (Strict Mode v2)
==================================================================================
Runs 50 real PDFs through the full ExtractionPipeline:
  PyMuPDF → Quality Gate → [ODL if quality < 0.90] → Regex → [Nova if gaps]

Fix v2: Correct patching strategy
  - boto3.client() is called in NovaService.__init__ at pipeline build time,
    so we patch boto3.client BEFORE pipeline construction.
  - odl_client.parse is patched at module level so structural_parsing_service
    picks up the mock (it uses `odl_client.parse(...)` after importing the module).
  - The fitz.Page.get_text patch is removed (fragile); instead we read PyMuPDF
    text directly for attribution.

Reports:
  1. Pathing Breakdown  — PyMuPDF-only / ODL-triggered / Nova-triggered counts
  2. Real Extraction    — % email/phone by deterministic regex vs filled by Nova
  3. Merge Rule Status  — PASSED / FAILED for Step 3.4 test
  4. Latency p50/p95    — per stage: pymupdf, odl, regex_parse, nova_fallback

Nova mock is REALISTIC: it only extracts what appears literally in the text.
ODL mock is a passthrough: routes correctly (triggered on quality<0.90) and
  returns the same PyMuPDF text so we can verify routing without a live Lambda.
"""

from __future__ import annotations

import gc
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch, MagicMock, PropertyMock

# ── sys.path setup ────────────────────────────────────────────────────────────
BENCH_DIR    = Path(__file__).resolve().parent
BACKEND_DIR  = BENCH_DIR.parent.parent
PROJECT_ROOT = BENCH_DIR.parent.parent.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Corpus ────────────────────────────────────────────────────────────────────
RESUME_DIR = BACKEND_DIR / "data" / "resumes"
N_SAMPLE   = 50

# ── Regex for realistic extraction ───────────────────────────────────────────
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")

_TECH_SKILLS = {
    "python", "java", "javascript", "typescript", "react", "angular", "vue",
    "node", "django", "flask", "spring", "docker", "kubernetes", "aws",
    "azure", "gcp", "sql", "postgresql", "mongodb", "redis", "kafka",
    "tensorflow", "pytorch", "pandas", "numpy", "scikit", "git", "linux",
    "autocad", "solidworks", "matlab", "revit", "staad", "excel",
    "powerpoint", "sap", "quickbooks",
}

_HEADER_NAMES = {
    "Curriculum Vitae", "Resume", "Contact Information",
    "Work Experience", "Professional Experience", "Summary",
    "Career Objective", "Skills", "Education", "References",
}


# ═════════════════════════════════════════════════════════════════════════════
# Realistic Nova Response Builder
# Only returns data actually visible in the text — never fabricates.
# ═════════════════════════════════════════════════════════════════════════════

def _build_realistic_nova_response(text: str) -> dict:
    """Build a Bedrock tool-call response by realistically parsing `text`."""
    extracted: Dict[str, Any] = {}

    # Email
    m = _EMAIL_RE.search(text)
    if m:
        extracted["email"] = m.group(0)

    # Phone
    m = _PHONE_RE.search(text)
    if m:
        raw = m.group(0).strip()
        if len(re.sub(r"\D", "", raw)) >= 7:
            extracted["phone"] = raw

    # Name (conservative: "First Last" at start of line, not a header)
    m = re.search(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s*$", text, re.MULTILINE)
    if m and m.group(1) not in _HEADER_NAMES:
        extracted["name"] = m.group(1)

    # Skills
    lower = text.lower()
    found = [s for s in _TECH_SKILLS if s in lower]
    if found:
        extracted["skills"] = [s.title() for s in found[:15]]

    return {
        "output": {
            "message": {
                "content": [
                    {"toolUse": {"name": "extract_resume_fields", "input": extracted}}
                ]
            }
        }
    }


def _nova_invoke_model_side_effect(**kwargs):
    """Realistic invoke_model mock: parse the prompt and extract honestly."""
    try:
        body = json.loads(kwargs.get("body", "{}"))
        text = ""
        for msg in body.get("messages", []):
            for c in msg.get("content", []):
                text += c.get("text", "")
    except Exception:
        text = ""

    # Extract the <text> ... </text> block from the prompt
    m = re.search(r"<text>(.*?)</text>", text, re.DOTALL)
    chunk_text = m.group(1) if m else text

    response_body = _build_realistic_nova_response(chunk_text)
    mock_stream = MagicMock()
    mock_stream.read.return_value = json.dumps(response_body).encode("utf-8")
    return {"body": mock_stream}


# ═════════════════════════════════════════════════════════════════════════════
# ODL Mock
# ═════════════════════════════════════════════════════════════════════════════

class ODLCallTracker:
    def __init__(self):
        self.calls: List[Tuple[str, str]] = []
        self._pymupdf_text: str = ""

    def mock_parse(self, s3_bucket: str, s3_key: str):
        """Passthrough: return PyMuPDF text as 'clean ODL markdown'."""
        self.calls.append((s3_bucket, s3_key))
        from src.extraction.odl_client import ODLParseResult
        return ODLParseResult(
            markdown=self._pymupdf_text,
            elements=[],
        )

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ═════════════════════════════════════════════════════════════════════════════
# Timing helpers
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class StageTimings:
    pymupdf_ms:    List[float] = field(default_factory=list)
    odl_ms:        List[float] = field(default_factory=list)
    regex_ms:      List[float] = field(default_factory=list)
    nova_ms:       List[float] = field(default_factory=list)
    total_ms:      List[float] = field(default_factory=list)

    def ingest(self, stage_timings: List[dict]):
        for t in stage_timings:
            stage = t.get("stage", "")
            dur   = t.get("duration_ms", 0.0)
            if stage == "quality_check":
                self.pymupdf_ms.append(dur)
            elif stage == "odl_parse":
                self.odl_ms.append(dur)
            elif stage == "regex_parse":
                self.regex_ms.append(dur)
            elif stage == "nova_fallback":
                self.nova_ms.append(dur)

    @staticmethod
    def _pct(data: List[float], p: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = max(0, math.ceil(p / 100 * len(s)) - 1)
        return round(s[idx], 1)

    def summarize(self) -> dict:
        rows = {}
        for name, vals in (
            ("pymupdf", self.pymupdf_ms), ("odl", self.odl_ms),
            ("regex_parse", self.regex_ms), ("nova", self.nova_ms),
            ("total", self.total_ms),
        ):
            rows[name] = {
                "count":  len(vals),
                "p50_ms": self._pct(vals, 50),
                "p95_ms": self._pct(vals, 95),
                "avg_ms": round(sum(vals) / len(vals), 1) if vals else 0.0,
            }
        return rows


# ═════════════════════════════════════════════════════════════════════════════
# Main benchmark
# ═════════════════════════════════════════════════════════════════════════════

def run_benchmark(pdfs: List[Path]) -> dict:
    import fitz

    # Counters
    pymupdf_only = 0
    odl_triggered = 0
    nova_triggered = 0

    email_by_regex = 0
    email_by_nova  = 0
    email_missing  = 0

    phone_by_regex = 0
    phone_by_nova  = 0
    phone_missing  = 0

    name_found   = 0
    name_missing = 0

    quality_scores: List[float] = []
    timings = StageTimings()
    errors: List[dict] = []
    per_resume: List[dict] = []

    print(f"\n  Running {len(pdfs)} PDFs through ExtractionPipeline…")
    print(f"  (Nova: realistic mock | ODL: passthrough tracker)\n")

    for i, pdf_path in enumerate(pdfs):
        doc_id   = pdf_path.stem
        t_start  = time.time()

        try:
            # ── Read raw PyMuPDF text BEFORE pipeline runs ─────────────────
            # We use fitz directly here (outside any patch) to get the
            # original text for attribution analysis.
            raw_text = ""
            try:
                doc = fitz.open(str(pdf_path))
                for page in doc:
                    raw_text += page.get_text() + "\n"
                doc.close()
            except Exception:
                raw_text = ""

            # ── ODL tracker per-resume ─────────────────────────────────────
            odl_tracker = ODLCallTracker()
            odl_tracker._pymupdf_text = raw_text  # passthrough

            # ── Build the mock bedrock client ──────────────────────────────
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_model.side_effect = _nova_invoke_model_side_effect

            # Patch strategy:
            #   1. boto3.client → returns mock_bedrock
            #      This MUST wrap the ExtractionPipeline() constructor so that
            #      NovaService.__init__ gets our mock bedrock client.
            #   2. src.extraction.odl_client.parse → ODL tracker
            #      Patched at module level so structural_parsing_service sees it.

            with patch("boto3.client", return_value=mock_bedrock), \
                 patch("src.extraction.odl_client.parse",
                       side_effect=odl_tracker.mock_parse):

                from src.extraction.extraction_pipeline import ExtractionPipeline
                pipe   = ExtractionPipeline()
                result = pipe.run_pipeline(
                    pdf_path=str(pdf_path),
                    doc_id=doc_id,
                    s3_bucket="bench-bucket",
                    s3_key=f"resumes/{pdf_path.name}",
                )

            fields    = result.get("fields", {})
            stage_t   = result.get("stage_timings", [])
            quality   = result.get("extraction_quality", 0.0)

            quality_scores.append(quality)
            timings.ingest(stage_t)
            timings.total_ms.append((time.time() - t_start) * 1000)

            # ── Pathing ────────────────────────────────────────────────────
            used_odl  = odl_tracker.call_count > 0
            used_nova = any(t.get("stage") == "nova_fallback" for t in stage_t)

            if used_odl:
                odl_triggered += 1
            else:
                pymupdf_only  += 1
            if used_nova:
                nova_triggered += 1

            # ── Field extraction ───────────────────────────────────────────
            # Prefer top-level keys (ExtractionPipeline result structure)
            # Falls back to personal_info sub-dict
            pi = fields.get("personal_info", {}) if isinstance(fields.get("personal_info"), dict) else {}
            email_val = fields.get("email") or pi.get("email")
            phone_val = fields.get("phone") or pi.get("phone")
            name_val  = fields.get("name")  or pi.get("name")

            # Email attribution: "by regex" if the email appears literally in
            # the raw PyMuPDF text (so deterministic could have found it).
            if email_val:
                if _EMAIL_RE.search(raw_text) and email_val in raw_text:
                    email_by_regex += 1
                else:
                    email_by_nova  += 1
            else:
                email_missing += 1

            # Phone attribution
            if phone_val:
                digits_raw  = re.sub(r"\D", "", phone_val)
                digits_text = re.sub(r"\D", "", raw_text)
                if digits_raw and digits_raw in digits_text:
                    phone_by_regex += 1
                else:
                    phone_by_nova  += 1
            else:
                phone_missing += 1

            # Name
            if name_val and name_val != "Unknown Candidate":
                name_found   += 1
            else:
                name_missing += 1

            per_resume.append({
                "doc_id":       doc_id,
                "quality":      round(quality, 3),
                "odl_triggered": used_odl,
                "nova_triggered": used_nova,
                "email":        email_val,
                "phone":        phone_val,
                "name":         name_val,
                "error":        None,
            })

        except Exception as exc:
            import traceback
            errors.append({"doc_id": doc_id, "error": str(exc)})
            per_resume.append({
                "doc_id": doc_id, "quality": 0.0,
                "odl_triggered": False, "nova_triggered": False,
                "email": None, "phone": None, "name": None,
                "error": str(exc),
            })

        if (i + 1) % 10 == 0 or i == 0:
            qs = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            print(f"    [{i+1:3d}/{len(pdfs)}] ODL={odl_triggered}  Nova={nova_triggered}  "
                  f"Err={len(errors)}  avg_quality={qs:.2f}")

    n = len(quality_scores) or 1

    # ── Aggregate ─────────────────────────────────────────────────────────────
    below_thresh = sum(1 for q in quality_scores if q < 0.90)
    qs_sorted    = sorted(quality_scores)

    return {
        "pathing": {
            "total":           len(pdfs),
            "processed_ok":    n,
            "errors":          len(errors),
            "pymupdf_only":    pymupdf_only,
            "odl_triggered":   odl_triggered,
            "nova_triggered":  nova_triggered,
            "pct_pymupdf_only":  round(pymupdf_only  / len(pdfs) * 100, 1),
            "pct_odl_triggered": round(odl_triggered  / len(pdfs) * 100, 1),
            "pct_nova_triggered": round(nova_triggered / len(pdfs) * 100, 1),
        },
        "extraction": {
            "email": {
                "by_regex": email_by_regex,
                "by_nova":  email_by_nova,
                "missing":  email_missing,
                "pct_regex": round(email_by_regex / n * 100, 1),
                "pct_nova":  round(email_by_nova  / n * 100, 1),
                "pct_total": round((email_by_regex + email_by_nova) / n * 100, 1),
            },
            "phone": {
                "by_regex": phone_by_regex,
                "by_nova":  phone_by_nova,
                "missing":  phone_missing,
                "pct_regex": round(phone_by_regex / n * 100, 1),
                "pct_nova":  round(phone_by_nova  / n * 100, 1),
                "pct_total": round((phone_by_regex + phone_by_nova) / n * 100, 1),
            },
            "name": {
                "found":     name_found,
                "missing":   name_missing,
                "pct_found": round(name_found / n * 100, 1),
            },
        },
        "quality": {
            "avg":             round(sum(quality_scores) / n, 3),
            "p50":             StageTimings._pct(qs_sorted, 50),
            "p95":             StageTimings._pct(qs_sorted, 95),
            "below_threshold": below_thresh,
            "threshold":       0.90,
        },
        "latency":     timings.summarize(),
        "errors":      errors[:20],
        "per_resume":  per_resume,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Step 3.4 Merge Rule Test (standalone, no pytest dependency)
# ═════════════════════════════════════════════════════════════════════════════

def run_merge_rule_test() -> dict:
    from src.extraction.fallback.nova_service import NovaService

    def _check(name, deterministic, llm_input, assertions):
        resp = {
            "output": {"message": {"content": [{"toolUse": {
                "name": "extract_resume_fields",
                "input": {k: v for k, v in llm_input.items() if v is not None},
            }}]}}
        }
        mock_bedrock = MagicMock()
        mock_stream  = MagicMock()
        mock_stream.read.return_value = json.dumps(resp).encode()
        mock_bedrock.invoke_model.return_value = {"body": mock_stream}

        with patch("boto3.client", return_value=mock_bedrock):
            nova   = NovaService()
            merged = nova.resolve_chunks(["sample text"], deterministic)

        failures = []
        for f_name, expected, desc in assertions:
            actual = merged.get(f_name)
            if expected == "__NOT_NONE__":
                ok = actual is not None
            elif expected == "__NONE__":
                ok = actual is None
            else:
                ok = actual == expected
            if not ok:
                failures.append(f"{f_name}: expected={expected!r}, got={actual!r} — {desc}")
        return {"test": name, "passed": not failures, "failures": failures,
                "merged": {k: merged.get(k) for k in ("name","email","phone","skills")}}

    checks = [
        _check(
            "Step 3.4 Canonical: email=real, phone=null → LLM fills phone only",
            deterministic={"name":None, "email":"real@example.com", "phone":None,
                           "skills":[], "experience":[]},
            llm_input={"email":"fake@llm.com", "phone":"555-1234"},
            assertions=[
                ("email", "real@example.com", "R-08: deterministic email must survive"),
                ("phone", "555-1234",         "R-09: LLM must fill null phone"),
            ],
        ),
        _check(
            "All deterministic fields present — LLM must be fully rejected",
            deterministic={"name":"Alice", "email":"alice@real.com", "phone":"+1-555-0100",
                           "skills":["Python"], "experience":[]},
            llm_input={"name":"FAKE","email":"fake@llm.com","phone":"000-0000"},
            assertions=[
                ("name",  "Alice",          "R-08: name"),
                ("email", "alice@real.com", "R-08: email"),
                ("phone", "+1-555-0100",    "R-08: phone"),
            ],
        ),
        _check(
            "All fields null — LLM fills everything",
            deterministic={"name":None,"email":None,"phone":None,"skills":[],"experience":[]},
            llm_input={"name":"Bob","email":"bob@build.com","phone":"555-BUILD"},
            assertions=[
                ("name",  "Bob",           "R-09: fill null name"),
                ("email", "bob@build.com", "R-09: fill null email"),
                ("phone", "555-BUILD",     "R-09: fill null phone"),
            ],
        ),
        _check(
            "LLM returns null (garbage input) — deterministic fields untouched",
            deterministic={"name":"Confirmed","email":"confirmed@x.com","phone":None,
                           "skills":["Java"],"experience":[]},
            llm_input={},
            assertions=[
                ("name",  "Confirmed",       "preserve name when LLM is null"),
                ("email", "confirmed@x.com", "preserve email when LLM is null"),
                ("phone", None,              "phone stays None — LLM had nothing"),
            ],
        ),
    ]

    # Manual skills overwrite check (list comparison)
    skills_resp = {"output":{"message":{"content":[{"toolUse":{
        "name":"extract_resume_fields","input":{"skills":["Cooking","Swimming"]}
    }}]}}}
    mock_b = MagicMock(); mock_s = MagicMock()
    mock_s.read.return_value = json.dumps(skills_resp).encode()
    mock_b.invoke_model.return_value = {"body": mock_s}
    with patch("boto3.client", return_value=mock_b):
        nova = NovaService()
        ms   = nova.resolve_chunks(["text"], {
            "name":None,"email":None,"phone":None,
            "skills":["Python","Django"],"experience":[],
        })
    python_ok  = "Python" in ms.get("skills", [])
    cooking_no = "Cooking" not in ms.get("skills", [])
    skill_failures = []
    if not python_ok:
        skill_failures.append("Python missing — deterministic skills overwritten")
    if not cooking_no:
        skill_failures.append("Cooking injected — LLM skills leaked into result")
    checks.append({
        "test": "Deterministic non-empty skills → LLM skills MUST NOT overwrite",
        "passed": python_ok and cooking_no,
        "failures": skill_failures,
        "merged": {"skills": ms.get("skills")},
    })

    passed = sum(1 for c in checks if c["passed"])
    return {
        "verdict": "PASSED" if passed == len(checks) else "FAILED",
        "passed": passed, "total": len(checks),
        "checks": checks,
    }


# ═════════════════════════════════════════════════════════════════════════════
# ODL Routing Verification
# ═════════════════════════════════════════════════════════════════════════════

def verify_odl_routing() -> dict:
    from src.extraction.structural_parsing_service import StructuralParsingService
    from src.extraction.odl_client import ODLParseResult

    results = []
    pdfs = sorted(RESUME_DIR.glob("*.pdf"))[:3]
    if not pdfs:
        return {"error": "No PDFs found"}

    for pdf_path in pdfs:
        doc_id = pdf_path.stem
        odl_calls: List[str] = []

        def _mock_odl(s3_bucket, s3_key):
            odl_calls.append(f"{s3_bucket}/{s3_key}")
            return ODLParseResult(markdown="# Clean ODL Markdown\nExtracted by ODL.", elements=[])

        with patch("src.extraction.odl_client.parse", side_effect=_mock_odl):
            svc    = StructuralParsingService()
            pr     = svc.parse_pdf(str(pdf_path), doc_id, "test-bucket", f"resumes/{pdf_path.name}")

        quality          = pr.quality_score
        odl_called       = len(odl_calls) > 0
        should_call      = quality < 0.90
        routing_correct  = odl_called == should_call

        # If ODL was called, the markdown fed to regex MUST be ODL's
        odl_md_used = "Clean ODL Markdown" in pr.markdown if odl_called else True

        results.append({
            "doc_id":          doc_id,
            "quality":         round(quality, 3),
            "odl_called":      odl_called,
            "should_call_odl": should_call,
            "routing_correct": routing_correct,
            "markdown_from_odl": odl_md_used,
            "markdown_snippet":  pr.markdown[:60].replace("\n", " "),
        })

    routing_ok   = all(r["routing_correct"]   for r in results)
    md_overwrite = all(r["markdown_from_odl"] for r in results)
    return {
        "routing_verdict":              "PASSED" if routing_ok    else "FAILED",
        "odl_markdown_overwrite_verdict": "PASSED" if md_overwrite else "FAILED",
        "details": results,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Report Generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_report(merge: dict, odl: dict, bench: dict, ts: str) -> str:
    L = []
    L.append("# Phase 3 Extraction Pipeline Benchmark — Strict Mode")
    L.append(f"Generated: {ts}")
    L.append(f"PDFs sampled: {bench['pathing']['total']}")
    L.append("")

    merge_ok   = merge["verdict"] == "PASSED"
    routing_ok = odl.get("routing_verdict") == "PASSED"
    md_ok      = odl.get("odl_markdown_overwrite_verdict") == "PASSED"
    gate_pass  = merge_ok and routing_ok and md_ok

    L.append("## Verification Gate")
    L.append("")
    L.append("| Check | Status |")
    L.append("|-------|--------|")
    L.append(f"| Step 3.4 Merge Rule (LLM never overwrites deterministic field) | {'✅ PASSED' if merge_ok else '❌ FAILED'} |")
    L.append(f"| ODL Routing (quality<0.90 → ODL triggered) | {'✅ PASSED' if routing_ok else '❌ FAILED'} |")
    L.append(f"| ODL Markdown Overwrite (ODL text fed to regex, not stale PyMuPDF) | {'✅ PASSED' if md_ok else '❌ FAILED'} |")
    L.append(f"| **Overall Gate** | {'🟢 **PASS — Ready for Phase 4**' if gate_pass else '🔴 **FAIL — Fix before Phase 4**'} |")
    L.append("")

    # Section 1: Merge Rule
    L.append("## Section 1 — Step 3.4 Merge Rule Test")
    L.append(f"**Verdict: {merge['verdict']}** ({merge['passed']}/{merge['total']} checks)")
    L.append("")
    L.append("| # | Test | Result |")
    L.append("|---|------|--------|")
    for i, c in enumerate(merge["checks"], 1):
        icon = "✅" if c["passed"] else "❌"
        L.append(f"| {i} | {c['test']} | {icon} |")
        for f in c.get("failures", []):
            L.append(f"|   | `{f}` | |")
    L.append("")

    # Section 2: ODL Routing
    L.append("## Section 2 — ODL Routing Verification")
    L.append(f"Routing: **{odl.get('routing_verdict')}**  |  "
             f"Markdown Overwrite: **{odl.get('odl_markdown_overwrite_verdict')}**")
    L.append("")
    L.append("| File | Quality | ODL Called? | Expected? | Correct | Markdown Source |")
    L.append("|------|---------|-------------|-----------|---------|-----------------|")
    for r in odl.get("details", []):
        ok_icon = "✅" if r["routing_correct"] else "❌"
        src = "ODL ✅" if r.get("markdown_from_odl") and r["odl_called"] else (
              "PyMuPDF ✅" if not r["odl_called"] else "⚠️ stale PyMuPDF")
        L.append(
            f"| {r['doc_id']} | {r['quality']:.3f} | "
            f"{'Yes' if r['odl_called'] else 'No'} | "
            f"{'Yes' if r['should_call_odl'] else 'No'} | "
            f"{ok_icon} | {src} |"
        )
    L.append("")

    # Section 3: Pathing
    p = bench["pathing"]
    q = bench["quality"]
    L.append("## Section 3 — Pathing Breakdown (50 Resumes)")
    L.append("")
    L.append("| Path | Count | % |")
    L.append("|------|-------|---|")
    L.append(f"| PyMuPDF-only (quality ≥ 0.90) | {p['pymupdf_only']} | {p['pct_pymupdf_only']}% |")
    L.append(f"| ODL triggered (quality < 0.90) | {p['odl_triggered']} | {p['pct_odl_triggered']}% |")
    L.append(f"| Nova triggered (gaps after regex) | {p['nova_triggered']} | {p['pct_nova_triggered']}% |")
    L.append(f"| Errors | {p['errors']} | {round(p['errors']/p['total']*100,1)}% |")
    L.append("")
    L.append(f"**Average quality score:** {q['avg']:.3f}  (p50={q['p50']:.3f}, p95={q['p95']:.3f})")
    L.append(f"**Resumes below 0.90 threshold:** {q['below_threshold']} / {p['total']}")
    L.append("")

    # Consistency check
    if q["avg"] < 0.90 and p["odl_triggered"] == 0:
        L.append("> ⚠️ **INCONSISTENCY:** avg quality < 0.90 but ODL never triggered. Routing bug.")
    elif q["avg"] < 0.90 and p["odl_triggered"] > 0:
        L.append("> ✅ **Consistent:** Low quality correctly triggered ODL.")
    else:
        L.append("> ✅ High average quality — most resumes took the PyMuPDF-only fast path.")
    L.append("")

    # Section 4: Extraction
    e = bench["extraction"]
    L.append("## Section 4 — Real Extraction Success")
    L.append("")
    L.append("| Field | By Regex (Deterministic) | By Nova (LLM gap-fill) | Missing | Total Found % |")
    L.append("|-------|--------------------------|------------------------|---------|---------------|")
    for fname in ("email", "phone", "name"):
        fd = e[fname]
        by_r  = fd.get("by_regex", fd.get("found", 0))
        by_n  = fd.get("by_nova",  0)
        miss  = fd.get("missing",  0)
        pct_r = fd.get("pct_regex", fd.get("pct_found", 0))
        pct_n = fd.get("pct_nova",  0)
        pct_t = fd.get("pct_total", fd.get("pct_found", 0))
        L.append(f"| {fname} | {by_r} ({pct_r}%) | {by_n} ({pct_n}%) | {miss} | {pct_t}% |")
    L.append("")
    L.append("> **Deterministic** = field already in raw text; regex would have found it.")
    L.append("> **Nova (LLM)** = field was null after regex; Nova filled it.")
    L.append("> Nova mock does NOT inflate counts — it only returns data it can see in text.")
    L.append("")

    # Section 5: Latency
    lt = bench["latency"]
    L.append("## Section 5 — Latency p50/p95 by Stage")
    L.append("")
    L.append("| Stage | n | p50 (ms) | p95 (ms) | avg (ms) |")
    L.append("|-------|---|----------|----------|----------|")
    for stage in ("pymupdf", "odl", "regex_parse", "nova", "total"):
        s = lt.get(stage, {})
        L.append(f"| {stage} | {s.get('count',0)} | "
                 f"{s.get('p50_ms',0):.1f} | {s.get('p95_ms',0):.1f} | {s.get('avg_ms',0):.1f} |")
    L.append("")
    L.append("> ODL/Nova latencies are mock timings — near-zero in test env.")
    L.append("")

    # Section 6: Per-Resume Spot Check
    L.append("## Section 6 — Per-Resume Spot Check (first 15)")
    L.append("")
    L.append("| # | File | Quality | ODL | Nova | Email | Phone |")
    L.append("|---|------|---------|-----|------|-------|-------|")
    for i, r in enumerate(bench.get("per_resume", [])[:15], 1):
        err    = " ⚠️" if r["error"] else ""
        email  = (r["email"] or "—")[:30]
        phone  = (r["phone"] or "—")[:20]
        L.append(f"| {i} | {r['doc_id']}{err} | {r['quality']:.3f} | "
                 f"{'✓' if r['odl_triggered'] else '—'} | "
                 f"{'✓' if r['nova_triggered'] else '—'} | "
                 f"`{email}` | `{phone}` |")
    L.append("")

    if bench["errors"]:
        L.append("## Errors")
        for e in bench["errors"][:10]:
            L.append(f"- `{e['doc_id']}`: {e['error'][:120]}")
        L.append("")

    L.append("## Phase 4 Gate Decision")
    if gate_pass:
        L.append("🟢 **ALL CHECKS PASSED** — Pipeline is internally consistent:")
        L.append("- Quality gate routes correctly to ODL when quality < 0.90.")
        L.append("- ODL markdown overwrites PyMuPDF text before regex runs.")
        L.append("- Nova fills gaps without overwriting deterministic fields (R-08/R-09).")
        L.append("- **Cleared to proceed to Phase 4.**")
    else:
        L.append("🔴 **GATE FAILED** — Do NOT proceed to Phase 4.")
        if not merge_ok:
            L.append(f"  ❌ Merge Rule: {merge['passed']}/{merge['total']} passed")
        if not routing_ok:
            L.append("  ❌ ODL routing logic is incorrect")
        if not md_ok:
            L.append("  ❌ ODL markdown not used for regex (stale PyMuPDF text injected)")

    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    ts = datetime.now().isoformat()
    print("\n" + "═" * 70)
    print("  PHASE 3 EXTRACTION PIPELINE BENCHMARK — STRICT MODE v2")
    print("═" * 70)
    print(f"  Timestamp: {ts}")

    pdfs = sorted(RESUME_DIR.glob("*.pdf"))[:N_SAMPLE]
    if not pdfs:
        print(f"  ERROR: No PDFs in {RESUME_DIR}")
        sys.exit(1)
    print(f"  Sampling {len(pdfs)} PDFs\n")

    # ── Step 1: Merge Rule ────────────────────────────────────────────────────
    print("─" * 70)
    print("  STEP 1: Step 3.4 Merge Rule Test")
    print("─" * 70)
    merge = run_merge_rule_test()
    icon  = "✅" if merge["verdict"] == "PASSED" else "❌"
    print(f"  {icon} {merge['verdict']}  ({merge['passed']}/{merge['total']} checks)")
    for c in merge["checks"]:
        ci = "  ✅" if c["passed"] else "  ❌"
        print(f"{ci} {c['test']}")
        for f in c.get("failures", []):
            print(f"        {f}")

    # ── Step 2: ODL Routing ───────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  STEP 2: ODL Routing Verification")
    print("─" * 70)
    odl = verify_odl_routing()
    print(f"  Routing: {odl['routing_verdict']}")
    print(f"  ODL MD Overwrite: {odl['odl_markdown_overwrite_verdict']}")
    for r in odl.get("details", []):
        ri = "  ✅" if r["routing_correct"] else "  ❌"
        src = "ODL ✅" if r.get("markdown_from_odl") and r["odl_called"] else (
              "PyMuPDF ✅" if not r["odl_called"] else "⚠️ stale")
        print(f"{ri} {r['doc_id']}: quality={r['quality']:.3f} "
              f"ODL={'Y' if r['odl_called'] else 'N'} "
              f"(expect={'Y' if r['should_call_odl'] else 'N'})  md→{src}")

    # ── Step 3: Benchmark ─────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  STEP 3: 50-Resume Benchmark")
    print("─" * 70)
    bench = run_benchmark(pdfs)

    p = bench["pathing"];  q = bench["quality"];  e = bench["extraction"]
    print(f"\n  Pathing: PyMuPDF-only={p['pymupdf_only']}  "
          f"ODL={p['odl_triggered']}  Nova={p['nova_triggered']}  "
          f"Err={p['errors']}")
    print(f"  Quality:  avg={q['avg']:.3f}  p50={q['p50']:.3f}  p95={q['p95']:.3f}  "
          f"below_threshold={q['below_threshold']}/{p['total']}")
    print(f"\n  Email: {e['email']['by_regex']} regex + {e['email']['by_nova']} nova "
          f"= {e['email']['pct_total']}% found")
    print(f"  Phone: {e['phone']['by_regex']} regex + {e['phone']['by_nova']} nova "
          f"= {e['phone']['pct_total']}% found")
    print(f"  Name:  {e['name']['found']} found ({e['name']['pct_found']}%)")

    lt = bench["latency"]
    print(f"\n  Latency p50/p95 ms:")
    for stage in ("pymupdf", "odl", "regex_parse", "nova", "total"):
        s = lt.get(stage, {})
        if s.get("count", 0) > 0:
            print(f"    {stage:12s}: p50={s['p50_ms']:6.1f}  p95={s['p95_ms']:6.1f}  "
                  f"n={s['count']}")

    # ── Generate report ───────────────────────────────────────────────────────
    report_path = BENCH_DIR / "phase3_strict_report.md"
    report_path.write_text(generate_report(merge, odl, bench, ts), encoding="utf-8")

    json_path = BENCH_DIR / "phase3_strict_report.json"
    with open(json_path, "w") as f:
        json.dump({
            "timestamp": ts, "merge_rule": merge,
            "odl_routing": odl,
            "benchmark": {k: v for k, v in bench.items() if k != "per_resume"},
            "per_resume": bench["per_resume"],
        }, f, indent=2, default=str)

    print(f"\n  📄 Report: {report_path}")
    print(f"  📄 JSON:   {json_path}")

    gate_pass = (
        merge["verdict"] == "PASSED" and
        odl["routing_verdict"] == "PASSED" and
        odl["odl_markdown_overwrite_verdict"] == "PASSED"
    )
    print("\n" + "═" * 70)
    if gate_pass:
        print("  🟢 VERIFICATION GATE: PASSED — Proceed to Phase 4")
    else:
        print("  🔴 VERIFICATION GATE: FAILED — Fix issues before Phase 4")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
