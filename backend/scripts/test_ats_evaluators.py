import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.deterministic_extraction_service import DeterministicExtractionService
from src.ats.ats_scoring_service import AtsScoringService

def test_ats_latency():
    print("Pre-computing Extractions (Simulating DB Fetch)...")
    
    resume_dir = Path("data/resumes")
    if not resume_dir.exists():
        resume_dir = Path("backend/data/resumes")
        if not resume_dir.exists():
            resume_dir = Path("../data/resumes")

    pdfs = list(resume_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {resume_dir}")
        return

    struct_svc = StructuralParsingService()
    extract_svc = DeterministicExtractionService()
    ats_svc = AtsScoringService()
    
    extractions = []
    
    for pdf in pdfs:
        with open(pdf, "rb") as f:
            pdf_bytes = f.read()
        try:
            structural = struct_svc.parse(pdf_bytes, pdf.name)
            ext_res = extract_svc.parse(structural, pdf.name)
            extractions.append(ext_res)
        except Exception as e:
            pass

    # Duplicate to 100 items
    benchmark_data = []
    while len(benchmark_data) < 100:
        benchmark_data.extend(extractions)
    benchmark_data = benchmark_data[:100]
    
    print(f"\nStarting ATS Scoring benchmark for {len(benchmark_data)} candidates...")
    
    import statistics
    latencies = []
    
    for ext_res in benchmark_data:
        start_time = time.perf_counter()
        
        try:
            res = ats_svc.score(ext_res)
            # just access to ensure it's generated
            score = res.ats_score
        except Exception as e:
            print(f"Error in ATS: {e}")
            
        end_time = time.perf_counter()
        latencies.append((end_time - start_time) * 1000)
        
    sorted_latencies = sorted(latencies)
    idx = int(0.95 * len(sorted_latencies))
    p95_latency = sorted_latencies[idx] if sorted_latencies else 0.0
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    
    print(f"\n--- ATS Benchmark Results ---")
    print(f"Evaluated {len(latencies)} candidates.")
    print(f"Average Latency: {avg_latency:.2f} ms")
    print(f"p95 Latency:     {p95_latency:.2f} ms")
    
    assert p95_latency < 100.0, f"ATS Latency regression: p95 is {p95_latency:.2f}ms (Target: < 100ms)"
    print("✅ Verification Gate Passed: p95 Latency < 100ms")

if __name__ == "__main__":
    test_ats_latency()
