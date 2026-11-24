#!/usr/bin/env python3
"""
scripts/run_concurrency_matrix.py — Concurrency Matrix Benchmark (Audited & Disaggregated)
========================================================================================
Empirically benchmarks ProcessPoolExecutor configurations across worker counts (1, 2, 3, 4, 6)
and four corpus sizes (5, 47, 100, 1000 documents) with 5 repetitions per configuration
(run 1 cold, runs 2-5 warm).

Timing boundaries are strictly separated:
1. Service Latency: Time from worker process start to worker process end (actual execution duration).
2. Queue Wait Latency: Time from task submission into executor to worker start.
3. Sojourn Latency: Total time from submission until result resolution in parent (queue + service + IPC).
4. IPC Overhead: Sojourn latency minus (queue wait + service latency).
5. True Pool Startup & Warm-up: Differentiates object instantiation from actual child process spawn & import.
6. Memory: Peak summed RSS, PSS, USS (from /proc/{pid}/smaps_rollup), and cgroup memory.
"""

import argparse
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
from pathlib import Path
import random
import resource
import statistics
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import fitz
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import pymupdf_layout_quality


def get_cgroup_memory_mb() -> float:
    """Read current cgroup memory usage if accessible."""
    for p in ["/sys/fs/cgroup/init.scope/memory.current", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"]:
        cgroup_path = Path(p)
        if cgroup_path.exists():
            try:
                bytes_val = int(cgroup_path.read_text().strip())
                return bytes_val / (1024.0 * 1024.0)
            except Exception:
                pass
    return 0.0


class ConcurrentMemorySampler:
    """Sample parent and all active descendant processes concurrent RSS, PSS, and USS."""

    def __init__(self, interval_sec: float = 0.015):
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.peak_rss_mb = 0.0
        self.peak_pss_mb = 0.0
        self.peak_uss_mb = 0.0
        self.peak_cgroup_mb = 0.0

    def _get_process_memory_mb(self, pid: int) -> Tuple[float, float, float]:
        rss = 0.0
        pss = 0.0
        uss = 0.0
        smaps_path = Path(f"/proc/{pid}/smaps_rollup")
        if smaps_path.exists():
            try:
                for line in smaps_path.read_text().splitlines():
                    if line.startswith("Rss:"):
                        rss = float(line.split()[1]) / 1024.0
                    elif line.startswith("Pss:"):
                        pss = float(line.split()[1]) / 1024.0
                    elif line.startswith("Private_Clean:"):
                        uss += float(line.split()[1]) / 1024.0
                    elif line.startswith("Private_Dirty:"):
                        uss += float(line.split()[1]) / 1024.0
                return rss, pss, uss
            except Exception:
                pass

        try:
            statm = Path(f"/proc/{pid}/statm").read_text().split()
            pages = int(statm[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
            rss = (pages * page_size) / (1024.0 * 1024.0)
            return rss, rss, rss
        except Exception:
            return 0.0, 0.0, 0.0

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
            tot_rss = 0.0
            tot_pss = 0.0
            tot_uss = 0.0
            for pid in pids:
                r, p, u = self._get_process_memory_mb(pid)
                tot_rss += r
                tot_pss += p
                tot_uss += u

            if tot_rss > self.peak_rss_mb:
                self.peak_rss_mb = tot_rss
            if tot_pss > self.peak_pss_mb:
                self.peak_pss_mb = tot_pss
            if tot_uss > self.peak_uss_mb:
                self.peak_uss_mb = tot_uss

            cg_mem = get_cgroup_memory_mb()
            if cg_mem > self.peak_cgroup_mb:
                self.peak_cgroup_mb = cg_mem

            time.sleep(self.interval_sec)

    def start(self) -> None:
        self._stop_event.clear()
        self.peak_rss_mb = 0.0
        self.peak_pss_mb = 0.0
        self.peak_uss_mb = 0.0
        self.peak_cgroup_mb = get_cgroup_memory_mb()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> Tuple[float, float, float, float]:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        return self.peak_rss_mb, self.peak_pss_mb, self.peak_uss_mb, self.peak_cgroup_mb


_worker_extractor: Optional[MarkdownExtractionService] = None


def _init_worker():
    global _worker_extractor
    _worker_extractor = MarkdownExtractionService()


def _ping_worker() -> bool:
    return True


def process_single_pdf_worker(pdf_path_str: str, submit_ts: float) -> Dict[str, Any]:
    global _worker_extractor
    t_start = time.perf_counter()
    queue_wait_ms = max(0.0, (t_start - submit_ts) * 1000.0)

    if _worker_extractor is None:
        _worker_extractor = MarkdownExtractionService()

    try:
        t0_pymupdf = time.perf_counter()
        with open(pdf_path_str, "rb") as f:
            pdf_bytes = f.read()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        scores = []
        page_texts = []
        for page in doc:
            p_text = page.get_text()
            p_words = page.get_text("words")
            p_drawings = len(page.get_drawings())
            score = pymupdf_layout_quality(page, text=p_text, words=p_words, drawings_count=p_drawings)
            scores.append(score)
            page_texts.append(p_text)
        doc.close()
        t1_pymupdf = time.perf_counter()

        t0_md = time.perf_counter()
        full_text = "\n".join(page_texts)
        res = _worker_extractor.extract(
            markdown_text=full_text,
            hyperlinks=[],
            elements=[],
            pymupdf_markdown="",
        )
        t1_md = time.perf_counter()
        t_end = time.perf_counter()

        return {
            "status": "success",
            "submit_ts": submit_ts,
            "worker_start_ts": t_start,
            "worker_end_ts": t_end,
            "queue_wait_ms": queue_wait_ms,
            "pymupdf_ms": (t1_pymupdf - t0_pymupdf) * 1000.0,
            "markdown_ms": (t1_md - t0_md) * 1000.0,
            "service_latency_ms": (t_end - t_start) * 1000.0,
            "name": res.get("fields", {}).get("name"),
        }
    except Exception as e:
        t_end = time.perf_counter()
        return {
            "status": "error",
            "submit_ts": submit_ts,
            "worker_start_ts": t_start,
            "worker_end_ts": t_end,
            "queue_wait_ms": queue_wait_ms,
            "pymupdf_ms": 0.0,
            "markdown_ms": 0.0,
            "service_latency_ms": (t_end - t_start) * 1000.0,
            "error": str(e),
        }


def calc_percentiles(values: List[float]) -> Tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    s = sorted(values)
    n = len(s)
    p50 = s[int(n * 0.50)]
    p95 = s[min(n - 1, int(math.ceil(n * 0.95)) - 1)]
    p99 = s[min(n - 1, int(math.ceil(n * 0.99)) - 1)]
    return round(p50, 1), round(p95, 1), round(p99, 1)


def run_single_benchmark_run(
    target_pdfs: List[Path],
    workers: int,
    is_cold: bool,
) -> Dict[str, Any]:
    mem_sampler = ConcurrentMemorySampler(interval_sec=0.015)
    mem_sampler.start()

    ru_self_0 = resource.getrusage(resource.RUSAGE_SELF)
    ru_child_0 = resource.getrusage(resource.RUSAGE_CHILDREN)

    pool_init_ms = 0.0
    pool_warmup_ms = 0.0
    pool_teardown_ms = 0.0

    service_latencies: List[float] = []
    queue_wait_latencies: List[float] = []
    sojourn_latencies: List[float] = []
    ipc_overheads: List[float] = []
    pymupdf_times: List[float] = []
    markdown_times: List[float] = []
    success_count = 0
    failure_count = 0

    t_wall_start = time.perf_counter()

    # Measure true pool startup and warm-up for all worker counts (including 1 worker)
    # to guarantee identical submission and timing boundaries.
    t0_init = time.perf_counter()
    executor = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker)
    t1_init = time.perf_counter()
    pool_init_ms = (t1_init - t0_init) * 1000.0

    warmup_futs = [executor.submit(_ping_worker) for _ in range(workers)]
    for f in warmup_futs:
        f.result()
    t2_warm = time.perf_counter()
    pool_warmup_ms = (t2_warm - t1_init) * 1000.0

    # Submit tasks into executor queue
    futures = []
    for p in target_pdfs:
        t_sub = time.perf_counter()
        fut = executor.submit(process_single_pdf_worker, str(p), t_sub)
        futures.append((fut, t_sub))

    for fut, t_sub in futures:
        try:
            r = fut.result(timeout=60)
            t_res = time.perf_counter()
            sojourn = (t_res - t_sub) * 1000.0
            service = r["service_latency_ms"]
            queue_w = r["queue_wait_ms"]
            ipc = max(0.0, sojourn - queue_w - service)

            service_latencies.append(service)
            queue_wait_latencies.append(queue_w)
            sojourn_latencies.append(sojourn)
            ipc_overheads.append(ipc)
            pymupdf_times.append(r["pymupdf_ms"])
            markdown_times.append(r["markdown_ms"])

            if r["status"] == "success":
                success_count += 1
            else:
                failure_count += 1
        except Exception:
            failure_count += 1

    t0_teardown = time.perf_counter()
    executor.shutdown(wait=True)
    pool_teardown_ms = (time.perf_counter() - t0_teardown) * 1000.0

    t_wall_end = time.perf_counter()
    peak_rss, peak_pss, peak_uss, peak_cgroup = mem_sampler.stop()

    ru_self_1 = resource.getrusage(resource.RUSAGE_SELF)
    ru_child_1 = resource.getrusage(resource.RUSAGE_CHILDREN)

    cpu_user = (ru_self_1.ru_utime - ru_self_0.ru_utime) + (ru_child_1.ru_utime - ru_child_0.ru_utime)
    cpu_sys = (ru_self_1.ru_stime - ru_self_0.ru_stime) + (ru_child_1.ru_stime - ru_child_0.ru_stime)
    total_cpu_time = cpu_user + cpu_sys
    wall_duration = t_wall_end - t_wall_start

    cpu_saturation_pct = (total_cpu_time / (wall_duration * workers)) * 100.0 if (wall_duration * workers > 0) else 0.0

    n = len(target_pdfs)
    throughput = n / wall_duration if wall_duration > 0 else 0.0

    srv_p50, srv_p95, srv_p99 = calc_percentiles(service_latencies)
    qw_p50, qw_p95, qw_p99 = calc_percentiles(queue_wait_latencies)
    soj_p50, soj_p95, soj_p99 = calc_percentiles(sojourn_latencies)

    return {
        "workers": workers,
        "is_cold": is_cold,
        "docs_count": n,
        "wall_duration_s": round(wall_duration, 3),
        "throughput_rps": round(throughput, 2),
        "total_cpu_s": round(total_cpu_time, 3),
        "cpu_user_s": round(cpu_user, 3),
        "cpu_sys_s": round(cpu_sys, 3),
        "cpu_saturation_pct": round(cpu_saturation_pct, 1),
        "service_latency": {
            "p50_ms": srv_p50,
            "p95_ms": srv_p95,
            "p99_ms": srv_p99,
            "mean_ms": round(statistics.mean(service_latencies), 1) if service_latencies else 0.0,
        },
        "queue_wait_latency": {
            "p50_ms": qw_p50,
            "p95_ms": qw_p95,
            "p99_ms": qw_p99,
            "mean_ms": round(statistics.mean(queue_wait_latencies), 1) if queue_wait_latencies else 0.0,
        },
        "sojourn_latency": {
            "p50_ms": soj_p50,
            "p95_ms": soj_p95,
            "p99_ms": soj_p99,
            "mean_ms": round(statistics.mean(sojourn_latencies), 1) if sojourn_latencies else 0.0,
        },
        "mean_ipc_overhead_ms": round(statistics.mean(ipc_overheads), 2) if ipc_overheads else 0.0,
        "mean_pymupdf_ms": round(statistics.mean(pymupdf_times), 2) if pymupdf_times else 0.0,
        "mean_markdown_ms": round(statistics.mean(markdown_times), 2) if markdown_times else 0.0,
        "peak_rss_mb": round(peak_rss, 1),
        "peak_pss_mb": round(peak_pss, 1),
        "peak_uss_mb": round(peak_uss, 1),
        "peak_cgroup_mb": round(peak_cgroup, 1),
        "pool_init_ms": round(pool_init_ms, 2),
        "pool_warmup_ms": round(pool_warmup_ms, 2),
        "pool_teardown_ms": round(pool_teardown_ms, 2),
        "success_count": success_count,
        "failure_count": failure_count,
    }


def run_benchmark_for_corpus(
    all_pdfs: List[Path],
    corpus_size: int,
    worker_configs: List[int],
    repetitions: int = 5,
) -> Dict[str, Any]:
    random.seed(42)
    target_pdfs = random.sample(all_pdfs, corpus_size) if len(all_pdfs) >= corpus_size else all_pdfs

    print(f"\n{'='*100}")
    print(f"  BENCHMARK SUITE: Corpus Size = {len(target_pdfs)} Resumes | Repetitions = {repetitions} (1 cold, {repetitions-1} warm)")
    print(f"  Worker counts: {worker_configs}")
    print(f"{'='*100}")

    corpus_results: Dict[int, List[Dict[str, Any]]] = {}

    for w in worker_configs:
        runs = []
        print(f"[*] Testing {w} worker(s)...", end="", flush=True)
        for r_idx in range(1, repetitions + 1):
            is_cold = (r_idx == 1)
            res = run_single_benchmark_run(target_pdfs, w, is_cold=is_cold)
            runs.append(res)
            label = "cold" if is_cold else f"warm{r_idx-1}"
            print(f" [{label}: {res['wall_duration_s']}s ({res['throughput_rps']:.1f} r/s, SrvP50 {res['service_latency']['p50_ms']}ms, RSS {res['peak_rss_mb']:.0f}MB)]", end="", flush=True)
        print(" -> DONE")
        corpus_results[w] = runs

    # Summary table separating Service Latency from Sojourn Latency
    summary_rows = []
    base_warm_wall = statistics.mean([r["wall_duration_s"] for r in corpus_results[1][1:]]) if len(corpus_results[1]) > 1 else corpus_results[1][0]["wall_duration_s"]

    for w in worker_configs:
        runs = corpus_results[w]
        cold_run = runs[0]
        warm_runs = runs[1:] if len(runs) > 1 else runs

        mean_wall = statistics.mean([r["wall_duration_s"] for r in warm_runs])
        mean_tps = statistics.mean([r["throughput_rps"] for r in warm_runs])

        # Service latency means across warm runs
        mean_srv_p50 = statistics.mean([r["service_latency"]["p50_ms"] for r in warm_runs])
        mean_srv_p95 = statistics.mean([r["service_latency"]["p95_ms"] for r in warm_runs])
        mean_srv_p99 = statistics.mean([r["service_latency"]["p99_ms"] for r in warm_runs])

        # Sojourn latency means across warm runs
        mean_soj_p50 = statistics.mean([r["sojourn_latency"]["p50_ms"] for r in warm_runs])
        mean_soj_p95 = statistics.mean([r["sojourn_latency"]["p95_ms"] for r in warm_runs])
        mean_soj_p99 = statistics.mean([r["sojourn_latency"]["p99_ms"] for r in warm_runs])

        # Queue wait means across warm runs
        mean_qw_p50 = statistics.mean([r["queue_wait_latency"]["p50_ms"] for r in warm_runs])

        # Memory averages across warm runs
        mean_rss = statistics.mean([r["peak_rss_mb"] for r in warm_runs])
        mean_pss = statistics.mean([r["peak_pss_mb"] for r in warm_runs])
        mean_uss = statistics.mean([r["peak_uss_mb"] for r in warm_runs])
        peak_rss = max([r["peak_rss_mb"] for r in runs])
        peak_pss = max([r["peak_pss_mb"] for r in runs])
        peak_uss = max([r["peak_uss_mb"] for r in runs])

        mean_warmup = statistics.mean([r["pool_warmup_ms"] for r in runs])
        mean_teardown = statistics.mean([r["pool_teardown_ms"] for r in runs])
        mean_sat = statistics.mean([r["cpu_saturation_pct"] for r in warm_runs])

        speedup = base_warm_wall / mean_wall if mean_wall > 0 else 1.0
        efficiency = (speedup / w) * 100.0

        summary_rows.append({
            "workers": w,
            "cold_wall_s": cold_run["wall_duration_s"],
            "warm_wall_s": round(mean_wall, 2),
            "warm_throughput_rps": round(mean_tps, 1),
            "service_p50_ms": round(mean_srv_p50, 1),
            "service_p95_ms": round(mean_srv_p95, 1),
            "service_p99_ms": round(mean_srv_p99, 1),
            "queue_p50_ms": round(mean_qw_p50, 1),
            "sojourn_p50_ms": round(mean_soj_p50, 1),
            "sojourn_p95_ms": round(mean_soj_p95, 1),
            "sojourn_p99_ms": round(mean_soj_p99, 1),
            "warm_rss_mb": round(mean_rss, 1),
            "warm_pss_mb": round(mean_pss, 1),
            "warm_uss_mb": round(mean_uss, 1),
            "peak_rss_mb": round(peak_rss, 1),
            "peak_pss_mb": round(peak_pss, 1),
            "peak_uss_mb": round(peak_uss, 1),
            "cpu_sat_pct": round(mean_sat, 1),
            "pool_warmup_ms": round(mean_warmup, 2),
            "pool_teardown_ms": round(mean_teardown, 2),
            "speedup": round(speedup, 2),
            "efficiency_pct": round(efficiency, 1),
        })

    print(f"\n{'-'*125}")
    print(f"  SUMMARY FOR CORPUS SIZE: {corpus_size} RESUMES (Warm Runs Averages)")
    print(f"{'-'*125}")
    print(f"Workers | Wall (s) | TPS (r/s) | Srv P50 (ms) | Srv P95 (ms) | Soj P50 (ms) | Soj P95 (ms) | Peak RSS | Peak PSS | Speedup | Efficiency")
    print(f"--------|----------|-----------|--------------|--------------|--------------|--------------|----------|----------|---------|-----------")
    for r in summary_rows:
        print(f"   {r['workers']:<4} | {r['warm_wall_s']:<8.2f} | {r['warm_throughput_rps']:<9.1f} | {r['service_p50_ms']:<12.1f} | {r['service_p95_ms']:<12.1f} | {r['sojourn_p50_ms']:<12.1f} | {r['sojourn_p95_ms']:<12.1f} | {r['peak_rss_mb']:<4.0f} MB   | {r['peak_pss_mb']:<4.0f} MB   | {r['speedup']:<5.2f}x  | {r['efficiency_pct']:<5.1f}%")

    return {
        "corpus_size": corpus_size,
        "summary": summary_rows,
        "raw_runs": corpus_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Resume Ranker Concurrency Matrix Benchmark")
    parser.add_argument("--sizes", type=str, default="5,47,100,1000", help="Comma-separated corpus sizes")
    parser.add_argument("--workers", type=str, default="1,2,3,4,6", help="Comma-separated worker counts")
    parser.add_argument("--repetitions", type=int, default=5, help="Number of repetitions per configuration")
    parser.add_argument("--output", type=str, default="concurrency_matrix_report.json", help="Output JSON path")
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    workers = [int(w.strip()) for w in args.workers.split(",") if w.strip()]

    corpus_dir = PROJECT_ROOT / "data" / "resumes"
    all_pdfs = sorted(list(corpus_dir.glob("*.pdf")))
    if not all_pdfs:
        print(f"Error: No PDFs found in {corpus_dir}")
        sys.exit(1)

    print(f"Starting Concurrency Matrix Suite across {len(all_pdfs)} available resumes")
    print(f"System: {os.cpu_count()} CPU cores, Python {sys.version.split()[0]}")

    results_by_size = {}
    for size in sizes:
        res = run_benchmark_for_corpus(
            all_pdfs=all_pdfs,
            corpus_size=size,
            worker_configs=workers,
            repetitions=args.repetitions,
        )
        results_by_size[str(size)] = res

    out_file = BACKEND_DIR / args.output
    with open(out_file, "w") as f:
        json.dump(
            {
                "system": {
                    "cpu_cores": os.cpu_count(),
                    "python_version": sys.version,
                    "corpus_total_available": len(all_pdfs),
                },
                "configurations": {
                    "corpus_sizes": sizes,
                    "worker_counts": workers,
                    "repetitions": args.repetitions,
                },
                "results": results_by_size,
            },
            f,
            indent=2,
        )
    print(f"\n[+] Full concurrency matrix benchmark written to {out_file}\n")


if __name__ == "__main__":
    main()
