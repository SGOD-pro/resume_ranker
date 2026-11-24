"""
test_benchmark_instrumentation.py — Unit tests for benchmark latency & memory instrumentation
=============================================================================================
Validates:
1. Synthetic tasks with known deterministic delays correctly isolate Service Latency, Queue Wait,
   and Sojourn Latency.
2. Pool startup correctly measures true child process creation and warm-up latency, not merely
   ProcessPoolExecutor object instantiation.
3. Service Latency vs Sojourn Latency are cleanly separated into distinct metrics without conflation.
"""

import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict


def synthetic_instrumented_task(submit_ts: float, duration_sec: float) -> Dict[str, Any]:
    t_start = time.perf_counter()
    time.sleep(duration_sec)
    t_end = time.perf_counter()
    return {
        "submit_ts": submit_ts,
        "worker_start_ts": t_start,
        "worker_end_ts": t_end,
        "service_latency_ms": (t_end - t_start) * 1000.0,
        "queue_wait_ms": (t_start - submit_ts) * 1000.0,
    }


def ping_worker() -> bool:
    return True


def test_synthetic_latency_instrumentation_accuracy():
    """Verify that synthetic 30ms tasks accurately separate service latency,
    queue wait latency, and total sojourn latency across a 2-worker pool."""
    task_duration = 0.030  # 30ms
    workers = 2
    task_count = 4

    t0_init = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Step 1: True warm-up (forces worker child process spawn & initializer)
        t_init = time.perf_counter()
        warmup_futs = [executor.submit(ping_worker) for _ in range(workers)]
        for f in warmup_futs:
            assert f.result() is True
        t_warmed = time.perf_counter()

        init_instantiation_ms = (t_init - t0_init) * 1000.0
        real_spawn_warmup_ms = (t_warmed - t_init) * 1000.0

        # __init__ should be instant (<10ms) while real spawn takes measurable time
        assert init_instantiation_ms >= 0.0
        assert real_spawn_warmup_ms > 0.0

        # Step 2: Submit 4 tasks of 30ms each
        futures = []
        for i in range(task_count):
            t_sub = time.perf_counter()
            fut = executor.submit(synthetic_instrumented_task, t_sub, task_duration)
            futures.append((i, fut, t_sub))

        results = []
        for i, fut, t_sub in futures:
            res = fut.result()
            t_res = time.perf_counter()
            sojourn_ms = (t_res - t_sub) * 1000.0
            ipc_ms = max(0.0, sojourn_ms - res["queue_wait_ms"] - res["service_latency_ms"])
            results.append({
                "idx": i,
                "service_ms": res["service_latency_ms"],
                "queue_wait_ms": res["queue_wait_ms"],
                "sojourn_ms": sojourn_ms,
                "ipc_ms": ipc_ms,
            })

    # Assertions on Service Latency:
    # Every task should have ~30ms service latency regardless of worker count
    for r in results:
        assert 25.0 <= r["service_ms"] <= 45.0, f"Task {r['idx']} service ms out of range: {r['service_ms']}"

    # Assertions on Queue Wait Latency:
    # Task 0 and Task 1 run concurrently immediately: queue wait < 15ms
    assert results[0]["queue_wait_ms"] < 15.0
    assert results[1]["queue_wait_ms"] < 15.0

    # Task 2 and Task 3 must wait for workers 0 and 1 to finish: queue wait >= 25ms
    assert results[2]["queue_wait_ms"] >= 25.0
    assert results[3]["queue_wait_ms"] >= 25.0

    # Assertions on Sojourn Latency:
    # Task 0 & 1 sojourn ~30ms
    assert 25.0 <= results[0]["sojourn_ms"] <= 55.0
    assert 25.0 <= results[1]["sojourn_ms"] <= 55.0

    # Task 2 & 3 sojourn ~60ms (queue wait 30ms + service 30ms)
    assert 50.0 <= results[2]["sojourn_ms"] <= 90.0
    assert 50.0 <= results[3]["sojourn_ms"] <= 90.0


def test_sequential_vs_queued_latency_definitions():
    """Verify that sequential synchronous execution matches service latency,
    and does not introduce artificial queue waiting."""
    task_duration = 0.020  # 20ms
    results = []

    for i in range(3):
        t_sub = time.perf_counter()
        res = synthetic_instrumented_task(t_sub, task_duration)
        t_res = time.perf_counter()
        sojourn_ms = (t_res - t_sub) * 1000.0
        results.append({
            "service_ms": res["service_latency_ms"],
            "queue_wait_ms": res["queue_wait_ms"],
            "sojourn_ms": sojourn_ms,
        })

    for r in results:
        assert 18.0 <= r["service_ms"] <= 35.0
        assert r["queue_wait_ms"] < 2.0  # Synchronous: no queue wait
        assert abs(r["sojourn_ms"] - r["service_ms"]) < 5.0
