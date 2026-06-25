"""
test_endpoints.py — Validate all API endpoints of the FastAPI backend.

Tests:
  1. GET /health
  2. POST /jobs (Create job)
  3. PATCH /jobs/{job_id} (Update job configuration)
  4. POST /jobs/{job_id}/resumes (Upload resume PDFs)
  5. GET /jobs/{job_id}/extract (Real resume extraction with SSE)
  6. POST /jobs/{job_id}/score (Rank candidates)
  7. GET /jobs/{job_id}/results (Get latest ranking results)
"""

import sys
from pathlib import Path
import json

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from src.api.app import app
from src.config.settings import RESUME_DIR


def test_api_flow():
    # Initialize the client. Under the hood, this will execute the lifespan
    # context manager, which verifies DynamoDB and S3 connectivity on startup.
    client = TestClient(app)

    # 1. Health check
    print("\n--- 1. Testing /health ---")
    resp = client.get("/health")
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    print("✅ Health check endpoint working correctly.")

    # 2. Create Job
    print("\n--- 2. Testing POST /jobs ---")
    job_data = {
        "title": "Senior Python Developer",
        "department": "Engineering",
        "description": "Looking for a senior python developer who knows FastAPI, Docker, and S3.",
        "must_have_skills": ["Python", "FastAPI"],
        "nice_to_have_skills": ["AWS", "Docker"],
        "min_years": 2,
        "max_years": 10,
        "education_level": "bachelor",
        "education_field": "Computer Science",
        "keywords": ["backend", "database"]
    }
    resp = client.post("/jobs", json=job_data)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    assert resp.status_code == 200
    res_json = resp.json()
    job_id = res_json["id"]
    assert job_id is not None
    print(f"✅ Job creation successful. Created Job ID: {job_id}")

    # 3. Update Job
    print(f"\n--- 3. Testing PATCH /jobs/{job_id} ---")
    update_data = {
        "nice_to_have_skills": ["AWS", "Docker", "S3", "DynamoDB"]
    }
    resp = client.patch(f"/jobs/{job_id}", json=update_data)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    print("✅ Job configuration update successful.")

    # 4. Upload Resumes
    print(f"\n--- 4. Testing POST /jobs/{job_id}/resumes ---")
    resume1_path = RESUME_DIR / "souvik.pdf"
    resume2_path = RESUME_DIR / "backend.pdf"

    print(f"Uploading resumes: {resume1_path.name}, {resume2_path.name}")
    with open(resume1_path, "rb") as r1, open(resume2_path, "rb") as r2:
        files = [
            ("files", (resume1_path.name, r1, "application/pdf")),
            ("files", (resume2_path.name, r2, "application/pdf")),
        ]
        resp = client.post(f"/jobs/{job_id}/resumes", files=files)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    assert resp.status_code == 200
    upload_res = resp.json()
    assert upload_res["total_accepted"] >= 2
    print("✅ Resume uploads accepted and saved to S3 successfully.")

    # 5. Extract Resumes (SSE stream)
    print(f"\n--- 5. Testing GET /jobs/{job_id}/extract (SSE stream) ---")
    events = []
    # TestClient's stream method enables iterating over the streaming response lines
    with client.stream("GET", f"/jobs/{job_id}/extract") as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line:
                print(f"  Stream Line: {line}")
                events.append(line)

    # Validate that we got progress and complete events
    assert any("event: progress" in e for e in events)
    assert any("event: complete" in e for e in events)
    print("✅ SSE extraction pipeline ran and streamed progress correctly.")

    # 6. Score Job
    print(f"\n--- 6. Testing POST /jobs/{job_id}/score ---")
    score_data = {
        "weights": {
            "skills": 40,
            "experience": 25,
            "keywords": 20,
            "education": 15
        }
    }
    resp = client.post(f"/jobs/{job_id}/score", json=score_data)
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200
    score_res = resp.json()
    print(f"Total Candidates Scored: {score_res['total_candidates']}")
    for cand in score_res["candidates"]:
        print(f"  - Name: {cand['name']}, Score: {cand['final_score']:.2f}%, Knocked Out: {cand['knocked_out']}")
        if cand['knocked_out']:
            print(f"    Reasons: {cand['knockout_reasons']}")
    
    assert len(score_res["candidates"]) > 0
    print("✅ Job candidate scoring completed successfully.")

    # 7. Get Results
    print(f"\n--- 7. Testing GET /jobs/{job_id}/results ---")
    resp = client.get(f"/jobs/{job_id}/results")
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200
    results_res = resp.json()
    assert results_res["job_id"] == job_id
    assert len(results_res["candidates"]) == len(score_res["candidates"])
    print("✅ Retrieval of stored results matches scored candidates.")

    print("\n🎉 ALL ENDPOINTS WORKING CORRECTLY!")


if __name__ == "__main__":
    test_api_flow()
