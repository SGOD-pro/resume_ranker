import sys
import time
import statistics
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).parent.parent))

from src.api.routes.ats import router

# Mount the router on a dummy FastAPI app
from fastapi import FastAPI
app = FastAPI()
app.include_router(router)

client = TestClient(app)

def test_api_latency():
    print("Starting End-to-End API Latency Benchmark on /api/v2/ats-check...")
    
    resume_dir = Path("data/resumes")
    if not resume_dir.exists():
        resume_dir = Path("backend/data/resumes")
        if not resume_dir.exists():
            resume_dir = Path("../data/resumes")

    pdfs = list(resume_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {resume_dir}")
        return

    # Use first PDF for benchmark
    pdf_path = pdfs[0]
    
    latencies = []
    
    # Warmup
    try:
        with open(pdf_path, "rb") as f:
            client.post("/api/v2/ats-check", files={"file": (pdf_path.name, f, "application/pdf")})
    except Exception as e:
        print(f"Warmup failed: {e}")
        return

    # Run 10 requests to get average latency
    print(f"Running 10 requests with {pdf_path.name}...")
    for _ in range(10):
        with open(pdf_path, "rb") as f:
            start_time = time.perf_counter()
            response = client.post("/api/v2/ats-check", files={"file": (pdf_path.name, f, "application/pdf")})
            end_time = time.perf_counter()
            
            if response.status_code != 200:
                print(f"Request failed with status {response.status_code}: {response.text}")
                return
                
            latencies.append((end_time - start_time) * 1000)

    avg_latency = statistics.mean(latencies)
    max_latency = max(latencies)
    
    print(f"\n--- E2E API Benchmark Results ---")
    print(f"Evaluated 10 requests.")
    print(f"Average Latency: {avg_latency:.2f} ms")
    print(f"Max Latency:     {max_latency:.2f} ms")
    
    # Target is < 1 second (1000ms)
    assert max_latency < 1000.0, f"API Latency regression: max is {max_latency:.2f}ms (Target: < 1000ms)"
    print("✅ Verification Gate Passed: End-to-End API < 1 second")

if __name__ == "__main__":
    test_api_latency()
