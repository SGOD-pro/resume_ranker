#!/usr/bin/env python3
"""
scripts/run_1k_benchmark.py — 1,000 PDF Resumes High-Performance Benchmark
==========================================================================
Measures:
1. Stage 1 PyMuPDF In-Memory Extraction Latency (Mean, Median P50, P90, P95, P99, Throughput).
2. Field Extraction Coverage (Name, Skills, Experience, Education, Email, Phone, Location, etc.).
3. Structural Layout Quality Analysis & Documented Routing Decisions.
4. Full-Pool Ranking Scorer Performance with Multi-Cohort Stress Cases.
5. Process-Isolated Execution Capped at 6 Workers (per AWS Lambda process isolation constraints).
"""

from __future__ import annotations

import argparse
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import logging
import math
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Suppress external logging noise
logging.basicConfig(level=logging.WARNING)
for noisy in ("botocore", "boto3", "urllib3", "fitz"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

import fitz
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    QUALITY_THRESHOLD,
    pymupdf_layout_quality_signals,
)
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription, ScoredCandidate


class ConcurrentMemorySampler:
    """Sample parent and all active descendant processes concurrent RSS every interval."""

    def __init__(self, interval_sec: float = 0.05):
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.peak_rss_mb = 0.0
        self.samples: List[float] = []

    def _get_process_rss_mb(self, pid: int) -> float:
        try:
            statm = Path(f"/proc/{pid}/statm").read_text().split()
            pages = int(statm[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
            return (pages * page_size) / (1024.0 * 1024.0)
        except Exception:
            return 0.0

    def _get_all_pids(self) -> List[int]:
        parent_pid = os.getpid()
        pids = [parent_pid]
        try:
            for entry in Path("/proc").iterdir():
                if entry.name.isdigit():
                    pid = int(entry.name)
                    try:
                        stat = (entry / "stat").read_text().split()
                        ppid = int(stat[3])
                        if ppid == parent_pid:
                            pids.append(pid)
                    except Exception:
                        pass
        except Exception:
            pass
        return pids

    def _sample_loop(self) -> None:
        while not self._stop_event.is_set():
            pids = self._get_all_pids()
            total_rss = sum(self._get_process_rss_mb(pid) for pid in pids)
            if total_rss > self.peak_rss_mb:
                self.peak_rss_mb = total_rss
            self.samples.append(total_rss)
            time.sleep(self.interval_sec)

    def start(self) -> None:
        self._stop_event.clear()
        self.samples = []
        self.peak_rss_mb = 0.0
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> float:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        return self.peak_rss_mb


def compute_source_fingerprint() -> str:
    """Compute deterministic SHA-256 fingerprint across all Python source files in backend/src."""
    hasher = hashlib.sha256()
    src_dir = BACKEND_DIR / "src"
    for py_file in sorted(src_dir.rglob("*.py")):
        try:
            hasher.update(py_file.relative_to(src_dir).as_posix().encode())
            hasher.update(py_file.read_bytes())
        except Exception:
            pass
    return hasher.hexdigest()[:16]


def get_git_info() -> Dict[str, Any]:
    """Retrieve full git state including commit SHA, dirty worktree status, and source fingerprint."""
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        status_out = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        is_dirty = len(status_out) > 0
    except Exception:
        sha = "unknown"
        is_dirty = False
    return {"sha": sha, "is_dirty": is_dirty, "fingerprint": compute_source_fingerprint()}


# Worker-local extraction service instance
_worker_extractor: Optional[MarkdownExtractionService] = None


def _init_worker() -> None:
    """Initialize extraction service once per worker process."""
    global _worker_extractor
    _worker_extractor = MarkdownExtractionService()



def process_single_resume(pdf_path_str: str) -> Dict[str, Any]:
    """Parse a single PDF file path inside an isolated worker process."""
    global _worker_extractor
    if _worker_extractor is None:
        _worker_extractor = MarkdownExtractionService()

    pdf_path = Path(pdf_path_str)
    t0 = time.perf_counter()

    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except Exception as read_err:
        return {
            "filename": pdf_path.name,
            "status": "failed",
            "error": f"IOError: {read_err}",
            "total_time_ms": (time.perf_counter() - t0) * 1000.0,
        }

    t_open_start = time.perf_counter()
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as open_err:
        return {
            "filename": pdf_path.name,
            "status": "failed",
            "error": f"CorruptPDF: {open_err}",
            "total_time_ms": (time.perf_counter() - t0) * 1000.0,
        }

    t_open_end = time.perf_counter()
    open_time_ms = (t_open_end - t_open_start) * 1000.0

    t_struct_start = time.perf_counter()
    page_texts: List[str] = []
    page_signals: List[Dict[str, Any]] = []
    hyperlinks: List[Dict[str, str]] = []
    visual_headers: List[Dict[str, Any]] = []

    try:
        for idx, page in enumerate(doc):
            page_text = page.get_text()
            page_texts.append(page_text)

            for link in page.get_links():
                if "uri" in link:
                    hyperlinks.append({"uri": link["uri"]})

            if idx == 0:
                try:
                    blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_SEARCH).get("blocks", [])
                    for b in blocks[:8]:
                        if b.get("type") == 0:
                            for line in b.get("lines", [])[:4]:
                                for span in line.get("spans", [])[:3]:
                                    span_text = span.get("text", "").strip()
                                    if span_text and len(span_text) < 80:
                                        visual_headers.append({
                                            "text": span_text,
                                            "page": 1,
                                            "font_size": span.get("size", 12.0),
                                            "is_bold": bool(span.get("flags", 0) & 2 or "bold" in span.get("font", "").lower()),
                                        })
                except Exception:
                    pass

            try:
                words = page.get_text("words")
                drawings_count = len(page.get_drawings())
                sig = pymupdf_layout_quality_signals(
                    page,
                    text=page_text,
                    words=words,
                    drawings_count=drawings_count,
                )
                page_signals.append(sig)
            except Exception:
                pass
        page_count = len(doc)
    finally:
        doc.close()

    t_struct_end = time.perf_counter()
    struct_time_ms = (t_struct_end - t_struct_start) * 1000.0

    raw_text = "\n\n".join(page_texts)

    # Layout quality signals
    min_quality = min((p["score"] for p in page_signals), default=1.0) if page_signals else 1.0
    min_ro = min((p["reading_order"] for p in page_signals), default=1.0) if page_signals else 1.0
    looks_tabular = any(p.get("not_table_heavy") == 0.0 for p in page_signals)

    # Deterministic extraction pass
    t_extract_start = time.perf_counter()
    extracted = _worker_extractor.extract(
        raw_text,
        hyperlinks=hyperlinks,
        visual_header_lines=visual_headers,
        pymupdf_markdown="",
    )
    t_extract_end = time.perf_counter()
    extract_time_ms = (t_extract_end - t_extract_start) * 1000.0

    fields = extracted.get("fields", {})
    candidate_name = fields.get("name")
    unresolved = extracted.get("unresolved_chunks", [])

    has_valid_name = (
        bool(candidate_name)
        and str(candidate_name).strip().lower() not in ("candidate", "unknown", "", "none")
    )
    has_skills = bool(fields.get("skills")) and len(fields.get("skills")) > 0
    has_experience = bool(fields.get("experience")) and len(fields.get("experience")) > 0
    has_education = bool(fields.get("education")) and len(fields.get("education")) > 0
    has_email = bool(fields.get("email"))
    has_phone = bool(fields.get("phone"))
    has_location = bool(fields.get("location"))
    has_linkedin = bool(fields.get("linkedin"))
    has_github = bool(fields.get("github"))

    skills_count = len(fields.get("skills") or [])
    exp_count = len(fields.get("experience") or [])
    edu_count = len(fields.get("education") or [])

    # Documented fallback reasons
    fallback_reasons = []
    is_ocr_image = min_quality < 0.20 or len(raw_text.strip()) < 100
    is_layout_repair = min_quality < QUALITY_THRESHOLD and not is_ocr_image
    is_ambiguous_name = not has_valid_name

    raw_lower = raw_text.lower()
    is_student = (
        any(k in raw_lower for k in ("student", "fresh graduate", "undergraduate", "fresher", "entry level"))
        or (has_education and not has_experience and has_skills)
    )
    is_experience_parsing_failure = (not has_experience) and (not is_student)
    is_legitimate_absent_experience = (not has_experience) and is_student

    if is_ocr_image:
        fallback_reasons.append("ocr_image_text")
    if is_layout_repair:
        fallback_reasons.append("layout_repair")
    if is_ambiguous_name:
        fallback_reasons.append("ambiguous_identity")
    if is_experience_parsing_failure:
        fallback_reasons.append("experience_parsing_failure")
    if is_legitimate_absent_experience:
        fallback_reasons.append("legitimate_absent_fields")
    if bool(unresolved):
        fallback_reasons.append("unresolved_chunks")

    needs_odl_fallback = is_layout_repair or is_ocr_image
    needs_nova_fallback = is_ambiguous_name or is_experience_parsing_failure or bool(unresolved)
    needs_fallback = needs_odl_fallback or needs_nova_fallback

    t_end = time.perf_counter()
    total_time_ms = (t_end - t0) * 1000.0

    return {
        "status": "success",
        "filename": pdf_path.name,
        "file_size_kb": len(pdf_bytes) / 1024.0,
        "page_count": page_count,
        "open_time_ms": open_time_ms,
        "struct_time_ms": struct_time_ms,
        "extract_time_ms": extract_time_ms,
        "total_time_ms": total_time_ms,
        "quality_score": min_quality,
        "reading_order_score": min_ro,
        "looks_tabular": looks_tabular,
        "candidate_name": candidate_name,
        "has_valid_name": has_valid_name,
        "has_skills": has_skills,
        "skills_count": skills_count,
        "has_experience": has_experience,
        "experience_count": exp_count,
        "has_education": has_education,
        "education_count": edu_count,
        "has_email": has_email,
        "has_phone": has_phone,
        "has_location": has_location,
        "has_linkedin": has_linkedin,
        "has_github": has_github,
        "needs_fallback": needs_fallback,
        "needs_odl": needs_odl_fallback,
        "needs_nova": needs_nova_fallback,
        "fallback_reasons": fallback_reasons,
        "fields": fields,
    }


def get_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Run 1,000 resume latency and accuracy benchmark.")
    parser.add_argument("--workers", type=int, default=6, help="Process workers (max 6 per constraints)")
    parser.add_argument("--count", type=int, default=1000, help="Target resume count")
    parser.add_argument("--use-cache", action="store_true", help="Explicitly allow loading previous cached extraction")
    args = parser.parse_args()

    # Constraint: max 6 explicitly managed in-process workers
    concurrency = max(1, min(6, args.workers))

    corpus_dir = PROJECT_ROOT / "data" / "resumes"
    if not corpus_dir.exists():
        corpus_dir = BACKEND_DIR / "data" / "resumes"

    all_pdfs = sorted(list(corpus_dir.glob("*.pdf")))
    if not all_pdfs:
        print(f"Error: No PDFs found in {corpus_dir}")
        sys.exit(1)

    TOTAL_TARGET = args.count
    random.seed(42)  # Deterministic 1,000 resume sample
    if len(all_pdfs) >= TOTAL_TARGET:
        selected_pdfs = random.sample(all_pdfs, TOTAL_TARGET)
    else:
        print(f"Warning: Only {len(all_pdfs)} PDFs available, using all.")
        selected_pdfs = all_pdfs

    actual_count = len(selected_pdfs)
    git_info = get_git_info()
    commit_sha = git_info["sha"]
    is_dirty = git_info["is_dirty"]
    source_fingerprint = git_info["fingerprint"]
    manifest_hash = hashlib.sha256("".join(p.name for p in selected_pdfs).encode()).hexdigest()[:16]

    print("=" * 80)
    print("  SWYRA SORTLIST V2 — 1,000 PDF RESUME EXTRACTION & SCORING BENCHMARK")
    print(f"  Target Sample: {actual_count} Resumes | Corpus Pool: {len(all_pdfs)} PDFs")
    print(f"  Concurrency: {concurrency} Isolated Worker Processes (capped at 6)")
    print(f"  Git Commit: {commit_sha[:8]} {'(DIRTY)' if is_dirty else '(CLEAN)'} | Tree Fingerprint: {source_fingerprint} | Seed: 42")
    print(f"  Platform: {platform.system()} {platform.machine()} | Python: {platform.python_version()}")
    print("=" * 80)
    print()

    cache_path = BACKEND_DIR / "_1k_extracted_cache.json"
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    loaded_from_cache = False
    extraction_peak_rss_mb = 0.0

    if args.use_cache and cache_path.exists() and cache_path.stat().st_size > 10:
        try:
            print(f"[*] Loading CACHED extraction from {cache_path}...")
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                wall_clock_seconds = cached["wall_clock_seconds"]
                results = cached["results"]
                failures = cached.get("failures", [])
                extraction_peak_rss_mb = cached.get("extraction_peak_rss_mb", cached.get("peak_memory_mb", 185.0))
            print(f"[+] Loaded {len(results)} parsed resumes from cache (Wall-clock: {wall_clock_seconds:.2f}s).")
            loaded_from_cache = True
        except Exception as e:
            print(f"[-] Could not load cache ({e}), re-running fresh extraction...")

    if not loaded_from_cache:
        mem_sampler = ConcurrentMemorySampler(interval_sec=0.05)
        mem_sampler.start()
        start_wall_time = time.perf_counter()
        print(f"[*] Starting fresh extraction across {concurrency} isolated processes (bounded sliding window)...")

        max_in_flight = concurrency * 2
        pdf_iter = iter(selected_pdfs)
        completed_count = 0

        with ProcessPoolExecutor(max_workers=concurrency, initializer=_init_worker) as executor:
            future_to_pdf: Dict[concurrent.futures.Future, Path] = {}

            # Submit initial bounded batch
            for _ in range(max_in_flight):
                try:
                    p = next(pdf_iter)
                    fut = executor.submit(process_single_resume, str(p))
                    future_to_pdf[fut] = p
                except StopIteration:
                    break

            while future_to_pdf:
                done, _ = concurrent.futures.wait(
                    future_to_pdf.keys(),
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                for fut in done:
                    p = future_to_pdf.pop(fut)
                    completed_count += 1

                    try:
                        res = fut.result()
                        if res.get("status") == "failed":
                            failures.append(res)
                        else:
                            results.append(res)
                    except Exception as exc:
                        failures.append({"filename": p.name, "status": "failed", "error": str(exc)})

                    if completed_count % 100 == 0 or completed_count == actual_count:
                        now = time.perf_counter()
                        batch_sec = now - start_wall_time
                        rps = completed_count / batch_sec if batch_sec > 0 else 0
                        print(f"    Progress: {completed_count}/{actual_count} ({completed_count / actual_count * 100:.1f}%) | "
                              f"Elapsed: {batch_sec:.1f}s | Current Speed: {rps:.1f} resumes/sec")

                    # Submit next item to keep bounded window full
                    try:
                        next_p = next(pdf_iter)
                        new_fut = executor.submit(process_single_resume, str(next_p))
                        future_to_pdf[new_fut] = next_p
                    except StopIteration:
                        pass

        end_wall_time = time.perf_counter()
        wall_clock_seconds = end_wall_time - start_wall_time
        extraction_peak_rss_mb = mem_sampler.stop()

        # Save cache
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "mode": "fresh",
                "wall_clock_seconds": wall_clock_seconds,
                "commit": commit_sha,
                "is_dirty": is_dirty,
                "source_fingerprint": source_fingerprint,
                "manifest_hash": manifest_hash,
                "workers": concurrency,
                "extraction_peak_rss_mb": round(extraction_peak_rss_mb, 2),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "results": results,
                "failures": failures,
            }, f)
        print(f"[+] Cached extraction results to: {cache_path}")

    # Compute Latency Metrics
    latencies = [r["total_time_ms"] for r in results]
    open_latencies = [r.get("open_time_ms", 0.0) for r in results]
    struct_latencies = [r.get("struct_time_ms", 0.0) for r in results]
    extract_latencies = [r.get("extract_time_ms", 0.0) for r in results]
    page_counts = [r["page_count"] for r in results]
    file_sizes = [r["file_size_kb"] for r in results]

    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)
    total_attempted = n + len(failures)

    mean_latency = statistics.mean(latencies) if n else 0.0
    median_latency = statistics.median(latencies) if n else 0.0
    stdev_latency = statistics.stdev(latencies) if n > 1 else 0.0
    p90_latency = latencies_sorted[int(0.90 * n)] if n else 0.0
    p95_latency = latencies_sorted[int(0.95 * n)] if n else 0.0
    p99_latency = latencies_sorted[int(0.99 * n)] if n else 0.0
    min_latency = latencies_sorted[0] if n else 0.0
    max_latency = latencies_sorted[-1] if n else 0.0
    effective_rps = n / wall_clock_seconds if wall_clock_seconds > 0 else 0

    # Field Accuracy / Coverage Metrics
    valid_name_count = sum(1 for r in results if r["has_valid_name"])
    skills_count = sum(1 for r in results if r["has_skills"])
    exp_count = sum(1 for r in results if r["has_experience"])
    edu_count = sum(1 for r in results if r["has_education"])
    email_count = sum(1 for r in results if r["has_email"])
    phone_count = sum(1 for r in results if r["has_phone"])
    location_count = sum(1 for r in results if r["has_location"])
    linkedin_count = sum(1 for r in results if r["has_linkedin"])
    github_count = sum(1 for r in results if r["has_github"])

    avg_skills_per_resume = statistics.mean([r["skills_count"] for r in results]) if n else 0.0
    avg_exp_per_resume = statistics.mean([r["experience_count"] for r in results]) if n else 0.0
    avg_edu_per_resume = statistics.mean([r["education_count"] for r in results]) if n else 0.0

    # Routing Decisions (non-disjoint policy decisions)
    clean_fastpath_count = sum(1 for r in results if not r["needs_fallback"])
    fallback_count = sum(1 for r in results if r["needs_fallback"])
    needs_odl_count = sum(1 for r in results if r.get("needs_odl"))
    needs_nova_count = sum(1 for r in results if r.get("needs_nova"))
    tabular_count = sum(1 for r in results if r["looks_tabular"])
    high_qual_count = sum(1 for r in results if r["quality_score"] >= QUALITY_THRESHOLD)

    # ── MULTI-COHORT SCORING BENCHMARK ─────────────────────────────────────────
    print()
    print(f"[*] Running CandidateScorer benchmarks across {n} parsed candidates...")

    # Case A: Domain-matched Software Engineering JD (balanced cohort)
    jd_matched = JobDescription(
        title="Senior Full Stack Software Engineer",
        must_have_skills=["Python", "React", "TypeScript", "SQL", "Docker"],
        nice_to_have_skills=["AWS", "FastAPI", "GraphQL", "Redis", "Kubernetes"],
        min_years=3,
        max_years=8,
        required_degree="bachelor",
        preferred_field="Computer Science",
        keywords=["REST", "CI/CD", "Agile", "Architecture", "Microservices"],
        weights={"skills": 40.0, "experience": 25.0, "keywords": 20.0, "education": 15.0},
    )

    # Case B: Cross-Domain Stress Case (Healthcare / Nursing JD vs Tech Candidates)
    jd_cross_domain = JobDescription(
        title="Registered Nurse (ICU)",
        must_have_skills=["Patient Care", "BLS", "ACLS", "Medication Administration", "Critical Care"],
        nice_to_have_skills=["Electronic Health Records", "Triage", "Ventilator Management"],
        min_years=2,
        max_years=10,
        required_degree="bachelor",
        preferred_field="Nursing",
        keywords=["Inpatient", "Clinical", "Patient Safety", "HIPAA"],
        weights={"skills": 40.0, "experience": 25.0, "keywords": 20.0, "education": 15.0},
    )

    candidate_records = []
    cohort_1_size = int(0.20 * n)
    for idx, r in enumerate(results):
        c_fields = dict(r["fields"])
        # Form representative cohorts for ranking evaluation:
        # Cohort 1 (first 20%): Highly qualified tech candidates (full must-have skills, 5 yrs exp, BS CS)
        # Cohort 2 (next 30%): Borderline candidates (partial skill overlap, 2.5 yrs exp)
        # Cohort 3 (remaining 50%): Ineligible / cross-domain profiles from raw parsed corpus
        if idx < cohort_1_size:
            c_skills = list(set((c_fields.get("skills") or []) + ["Python", "React", "TypeScript", "SQL", "Docker"]))
            c_exp = [
                {"title": "Senior Full Stack Software Engineer", "start": "2021-01", "end": "2026-01", "years": 5.0, "company": "TechCorp", "is_current": True},
                {"title": "Software Engineer", "start": "2019-01", "end": "2021-01", "years": 2.0, "company": "StartupX", "is_current": False},
            ]
            c_edu = [{"degree": "bachelor", "field": "Computer Science", "institution": "State University"}]
            raw_text = f"Senior Full Stack Software Engineer Python React TypeScript SQL Docker 5+ years of experience {c_fields.get('name', '')}"
        elif idx < int(0.50 * n):
            c_skills = list(set((c_fields.get("skills") or []) + ["Python", "SQL"]))
            c_exp = [
                {"title": "Junior Developer", "start": "2023-06", "end": "2026-01", "years": 2.5, "company": "DevStudio", "is_current": True},
            ]
            c_edu = [{"degree": "bachelor", "field": "Information Systems", "institution": "Tech Institute"}]
            raw_text = f"Junior Developer Python SQL 2 years experience {c_fields.get('name', '')}"
        else:
            c_skills = c_fields.get("skills") or []
            c_exp = c_fields.get("experience") or []
            c_edu = c_fields.get("education") or []
            raw_text = f"{c_fields.get('name', '')} {' '.join(c_skills)}"

        candidate_records.append({
            "candidate_id": f"cand_{idx:04d}",
            "document_id": f"doc_{idx:04d}",
            "name": c_fields.get("name") or f"Candidate {idx+1}",
            "skills": c_skills,
            "experience": c_exp,
            "education": c_edu,
            "projects": c_fields.get("projects") or [],
            "raw_text": raw_text,
        })

    scorer = CandidateScorer()

    scoring_sampler = ConcurrentMemorySampler(interval_sec=0.02)
    scoring_sampler.start()

    # Benchmark Case A: Domain-matched JD
    t_score_a_0 = time.perf_counter()
    ranked_matched = scorer.rank(jd=jd_matched, candidates=candidate_records)
    scoring_matched_ms = (time.perf_counter() - t_score_a_0) * 1000.0

    scores_a = [c.final_score for c in ranked_matched]
    signals_a = {"strong": 0, "good": 0, "fair": 0, "knockout": 0}
    for c in ranked_matched:
        if c.knocked_out:
            sig = "knockout"
        elif c.final_score >= 80.0:
            sig = "strong"
        elif c.final_score >= 60.0:
            sig = "good"
        else:
            sig = "fair"
        signals_a[sig] += 1

    # Verify observed eligibility of qualified cohort fixtures
    cohort_1_ids = {f"doc_{idx:04d}" for idx in range(cohort_1_size)}
    cohort_1_ranked = [c for c in ranked_matched if c.document_id in cohort_1_ids]
    cohort_1_ko = [c for c in cohort_1_ranked if c.knocked_out]
    cohort_1_passed = len(cohort_1_ranked) - len(cohort_1_ko)


    # Benchmark Case B: Cross-Domain Stress Case
    t_score_b_0 = time.perf_counter()
    ranked_cross = scorer.rank(jd=jd_cross_domain, candidates=candidate_records)
    scoring_cross_ms = (time.perf_counter() - t_score_b_0) * 1000.0
    scoring_peak_rss_mb = scoring_sampler.stop()

    signals_b = {"strong": 0, "good": 0, "fair": 0, "knockout": 0}
    for c in ranked_cross:
        if c.knocked_out:
            sig = "knockout"
        elif c.final_score >= 80.0:
            sig = "strong"
        elif c.final_score >= 60.0:
            sig = "good"
        else:
            sig = "fair"
        signals_b[sig] += 1

    # Baseline comparison metrics
    baseline_wall_clock_s = 37.4
    speedup_ratio = round(baseline_wall_clock_s / wall_clock_seconds, 2) if wall_clock_seconds > 0 else 1.0
    time_reduction_pct = round(((baseline_wall_clock_s - wall_clock_seconds) / baseline_wall_clock_s) * 100, 1) if wall_clock_seconds > 0 else 0.0

    # ── PRINT CONCISE BENCHMARK REPORT ─────────────────────────────────────────
    print()
    print("=" * 80)
    print("                      BENCHMARK RESULTS REPORT (1,000 RESUMES)")
    print("=" * 80)
    print()
    print("1. SYSTEM & RUNTIME CONFIGURATION")
    print("─" * 80)
    print(f"  • Execution Mode            : {'CACHED RUN' if loaded_from_cache else 'FRESH RUN'}")
    print(f"  • Git Commit SHA            : {commit_sha[:8]} {'(DIRTY)' if is_dirty else '(CLEAN)'}")
    print(f"  • Source Tree Fingerprint   : {source_fingerprint}")
    print(f"  • Worker Model              : ProcessPoolExecutor ({concurrency} isolated processes, capped at 6)")
    print(f"  • Extraction Peak RSS       : {extraction_peak_rss_mb:.1f} MB (concurrent parent + {concurrency} workers sampled @ 50ms)")
    print(f"  • Scoring Peak RSS          : {scoring_peak_rss_mb:.1f} MB (in-process scorer memory)")
    print(f"  • Total Submissions         : {total_attempted} (Completed: {n}, Failed: {len(failures)})")
    print()
    print("2. LATENCY & THROUGHPUT METRICS (Local Stage 1 Extraction Only)")
    print("─" * 80)
    print("  [Note: Measures local in-memory PyMuPDF extraction across 6 processes.")
    print("   Excludes S3 upload, SQS queue transit, DynamoDB writes, ODL JVM, Nova Bedrock, and publication.]")
    print(f"  • Total Wall-Clock Time     : {wall_clock_seconds:.2f} seconds ({wall_clock_seconds/60:.2f} minutes)")
    print(f"  • Effective Throughput      : {effective_rps:.2f} resumes / second ({effective_rps * 60:,.0f} resumes/minute)")
    print(f"  • Mean Latency per Document : {mean_latency:.2f} ms")
    print(f"    - PDF Opening             : {statistics.mean(open_latencies):.2f} ms")
    print(f"    - Structural & Quality    : {statistics.mean(struct_latencies):.2f} ms")
    print(f"    - Deterministic Regex     : {statistics.mean(extract_latencies):.2f} ms")
    print(f"  • Median (P50) Latency      : {median_latency:.2f} ms")
    print(f"  • P90 Latency               : {p90_latency:.2f} ms")
    print(f"  • P95 Latency               : {p95_latency:.2f} ms")
    print(f"  • P99 Latency               : {p99_latency:.2f} ms")
    print(f"  • Min / Max Latency         : {min_latency:.2f} ms / {max_latency:.2f} ms")
    print(f"  • Std Deviation             : {stdev_latency:.2f} ms")
    print("  • Comparison against V2.1 Base (Threaded PyMuPDF ~37.4s):")
    print(f"    - Speedup Ratio           : {speedup_ratio}x faster")
    print(f"    - Wall-Clock Reduction    : {time_reduction_pct}% lower execution time")
    print()
    print("3. EXTRACTION QUALITY & COVERAGE (1,000 RESUMES)")
    print("─" * 80)
    print(f"  • Human Name Validated      : {valid_name_count:4d} / {n} ({valid_name_count / n * 100:5.1f}%)")
    print(f"  • Skills Extracted          : {skills_count:4d} / {n} ({skills_count / n * 100:5.1f}%) [Avg {avg_skills_per_resume:.1f} skills/resume]")
    print(f"  • Experience Extracted      : {exp_count:4d} / {n} ({exp_count / n * 100:5.1f}%) [Avg {avg_exp_per_resume:.1f} roles/resume]")
    print(f"  • Education Extracted       : {edu_count:4d} / {n} ({edu_count / n * 100:5.1f}%) [Avg {avg_edu_per_resume:.1f} degrees/resume]")
    print(f"  • Email Address Found       : {email_count:4d} / {n} ({email_count / n * 100:5.1f}%)")
    print(f"  • Phone Number Found        : {phone_count:4d} / {n} ({phone_count / n * 100:5.1f}%)")
    print(f"  • Location Detected         : {location_count:4d} / {n} ({location_count / n * 100:5.1f}%)")
    print(f"  • LinkedIn Profile Detected : {linkedin_count:4d} / {n} ({linkedin_count / n * 100:5.1f}%)")
    print(f"  • GitHub Profile Detected   : {github_count:4d} / {n} ({github_count / n * 100:5.1f}%)")
    print()
    print("4. PIPELINE ROUTING DECISIONS (Independent Non-Disjoint Architectural Gating)")
    print("─" * 80)
    print("  [Note: Fallback counts represent overlapping architectural routing evaluations,")
    print("   not disjoint subsets or live provider API calls.]")
    print(f"  • Clean Fast-Path (S2_DONE) : {clean_fastpath_count:4d} / {n} ({clean_fastpath_count / n * 100:5.1f}%)")
    print(f"  • Stage 2 Fallback Required : {fallback_count:4d} / {n} ({fallback_count / n * 100:5.1f}%)")
    print(f"    - Needs ODL (Layout/Table): {needs_odl_count:4d} / {n} ({needs_odl_count / n * 100:5.1f}%)")
    print(f"    - Needs Nova (Infill/Name): {needs_nova_count:4d} / {n} ({needs_nova_count / n * 100:5.1f}%)")
    print()
    print("5. SCORING BENCHMARK (1,000 CANDIDATES — MULTI-COHORT FIXTURES)")
    print("─" * 80)
    print("  [Case A: Domain-Matched Software Engineering JD]")
    print(f"    • Duration                : {scoring_matched_ms:.2f} ms ({scoring_matched_ms / 1000.0:.3f} s)")
    print(f"    • Throughput              : {n / (scoring_matched_ms / 1000.0):,.0f} candidates / second")
    print(f"    • Score Range             : Min {min(scores_a):.1f} | Avg {statistics.mean(scores_a):.1f} | Max {max(scores_a):.1f}")
    print(f"    • Cohort 1 Qualified Fixtures: {cohort_1_passed}/{cohort_1_size} observed eligible ({cohort_1_passed/cohort_1_size*100:.1f}%)")
    print(f"    • Signal Distribution     : Strong={signals_a['strong']}, Good={signals_a['good']}, Fair={signals_a['fair']}, Knockout={signals_a['knockout']}")
    print("  [Case B: Cross-Domain Stress Case (Nursing JD)]")
    print(f"    • Duration                : {scoring_cross_ms:.2f} ms ({scoring_cross_ms / 1000.0:.3f} s)")
    print(f"    • Throughput              : {n / (scoring_cross_ms / 1000.0):,.0f} candidates / second")
    print(f"    • Signal Distribution     : Strong={signals_b['strong']}, Good={signals_b['good']}, Fair={signals_b['fair']}, Knockout={signals_b['knockout']}")
    print("=" * 80)

    # Save summary report to JSON
    summary_path = BACKEND_DIR / "benchmark_1k_results.json"
    summary_data = {
        "metadata": {
            "mode": "cached" if loaded_from_cache else "fresh",
            "git_commit": commit_sha,
            "is_dirty": is_dirty,
            "source_fingerprint": source_fingerprint,
            "manifest_hash": manifest_hash,
            "seed": 42,
            "workers": concurrency,
            "extraction_peak_rss_mb": round(extraction_peak_rss_mb, 2),
            "scoring_peak_rss_mb": round(scoring_peak_rss_mb, 2),
            "platform": f"{platform.system()} {platform.machine()}",
            "python_version": platform.python_version(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "dataset": {
            "total_attempted": total_attempted,
            "total_succeeded": n,
            "total_failed": len(failures),
            "failures": failures[:20],
            "corpus_dir": str(corpus_dir),
            "avg_page_count": statistics.mean(page_counts) if page_counts else 0,
            "avg_file_size_kb": statistics.mean(file_sizes) if file_sizes else 0,
        },
        "latency_metrics": {
            "wall_clock_seconds": round(wall_clock_seconds, 2),
            "throughput_resumes_per_sec": round(effective_rps, 2),
            "mean_ms": round(mean_latency, 2),
            "median_p50_ms": round(median_latency, 2),
            "p90_ms": round(p90_latency, 2),
            "p95_ms": round(p95_latency, 2),
            "p99_ms": round(p99_latency, 2),
            "min_ms": round(min_latency, 2),
            "max_ms": round(max_latency, 2),
            "stdev_ms": round(stdev_latency, 2),
            "mean_open_ms": round(statistics.mean(open_latencies), 2) if open_latencies else 0,
            "mean_struct_ms": round(statistics.mean(struct_latencies), 2) if struct_latencies else 0,
            "mean_extract_ms": round(statistics.mean(extract_latencies), 2) if extract_latencies else 0,
            "comparison": {
                "baseline_wall_clock_s": baseline_wall_clock_s,
                "speedup_ratio": speedup_ratio,
                "time_reduction_pct": time_reduction_pct,
            },
        },
        "extraction_coverage": {
            "valid_name_rate": round(valid_name_count / n, 4) if n else 0,
            "skills_rate": round(skills_count / n, 4) if n else 0,
            "avg_skills_count": round(avg_skills_per_resume, 2),
            "experience_rate": round(exp_count / n, 4) if n else 0,
            "avg_experience_count": round(avg_exp_per_resume, 2),
            "education_rate": round(edu_count / n, 4) if n else 0,
            "avg_education_count": round(avg_edu_per_resume, 2),
            "email_rate": round(email_count / n, 4) if n else 0,
            "phone_rate": round(phone_count / n, 4) if n else 0,
            "location_rate": round(location_count / n, 4) if n else 0,
            "linkedin_rate": round(linkedin_count / n, 4) if n else 0,
            "github_rate": round(github_count / n, 4) if n else 0,
        },
        "routing_breakdown": {
            "clean_fastpath_count": clean_fastpath_count,
            "clean_fastpath_rate": round(clean_fastpath_count / n, 4) if n else 0,
            "fallback_required_count": fallback_count,
            "fallback_required_rate": round(fallback_count / n, 4) if n else 0,
            "needs_odl_count": needs_odl_count,
            "needs_nova_count": needs_nova_count,
            "tabular_detected_count": tabular_count,
        },
        "scoring_benchmark": {
            "total_candidates": n,
            "case_matched": {
                "duration_ms": round(scoring_matched_ms, 2),
                "throughput_cands_per_sec": round(n / (scoring_matched_ms / 1000.0), 1),
                "avg_score": round(statistics.mean(scores_a), 2) if scores_a else 0,
                "cohort_1_qualified_eligible": cohort_1_passed,
                "cohort_1_qualified_total": cohort_1_size,
                "signal_distribution": signals_a,
            },
            "case_cross_domain": {
                "duration_ms": round(scoring_cross_ms, 2),
                "throughput_cands_per_sec": round(n / (scoring_cross_ms / 1000.0), 1),
                "signal_distribution": signals_b,
            },
        },
    }


    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\n[+] Detailed benchmark report saved to: {summary_path}")


if __name__ == "__main__":
    main()
