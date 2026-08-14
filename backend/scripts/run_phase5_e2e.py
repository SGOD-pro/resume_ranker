import os
import glob
import time
import json
import random
import httpx

API_BASE = "http://localhost:8000/api/v2"

def main():
    print("=== Starting E2E Test for Resume Ranker & ATS Checker ===")
    
    # 1. Create a Job
    job_payload = {
        "title": "Senior Software Engineer",
        "department": "Engineering",
        "description": "We are looking for a Senior Software Engineer with strong Python and React skills.",
        "must_have_skills": ["Python", "React", "AWS", "SQL"],
        "nice_to_have_skills": ["TypeScript", "Docker", "Kubernetes"],
        "min_years": 5,
        "max_years": 15,
        "required_degree": "bachelor",
        "keywords": ["Microservices", "API", "Agile"]
    }
    
    print("\n1. Creating Job...")
    res = httpx.post(f"{API_BASE}/jobs", json=job_payload)
    res.raise_for_status()
    job_id = res.json()["job_id"]
    print(f"Created Job ID: {job_id}")
    
    # 2. Get 20 random PDFs
    pdf_files = glob.glob("/mnt/d/WORK/resume_ranker/backend/tests/fixtures/pdfs/*.pdf")
    if not pdf_files:
        # Fallback to current directory or some known path
        pdf_files = glob.glob("../../tests/fixtures/pdfs/*.pdf")
    if len(pdf_files) > 20:
        pdf_files = random.sample(pdf_files, 20)
    
    print(f"\n2. Found {len(pdf_files)} PDFs for testing.")
    if not pdf_files:
        print("No PDFs found to test with.")
        return
        
    # 3. Test ATS Checker on these PDFs
    print("\n3. Testing Standalone ATS Checker on 5 random PDFs...")
    ats_test_files = random.sample(pdf_files, min(5, len(pdf_files)))
    for pdf_path in ats_test_files:
        print(f"\nRunning ATS check on: {os.path.basename(pdf_path)}")
        with open(pdf_path, 'rb') as f:
            ats_res = httpx.post(f"{API_BASE}/ats-check", files={"file": f})
            if ats_res.status_code == 200:
                data = ats_res.json()
                print(f"  ATS Score: {data.get('score')}")
                if data.get("flags"):
                    print(f"  Flags: {data.get('flags')}")
                else:
                    print("  No severe flags.")
            else:
                print(f"  ATS Check Failed: {ats_res.text}")
                
    # 4. Upload Resumes to Job
    print(f"\n4. Uploading {len(pdf_files)} Resumes to Job...")
    upload_files = []
    file_handles = []
    for pdf_path in pdf_files:
        f = open(pdf_path, 'rb')
        file_handles.append(f)
        upload_files.append(("files", (os.path.basename(pdf_path), f, "application/pdf")))
        
    res = httpx.post(f"{API_BASE}/jobs/{job_id}/resumes/upload", files=upload_files)
    for f in file_handles:
        f.close()
    res.raise_for_status()
    print(f"Upload successful. Uploaded {len(pdf_files)} files.")
    
    # 5. Extract
    print("\n5. Starting Extraction...")
    res = httpx.post(f"{API_BASE}/jobs/{job_id}/resumes/extract")
    res.raise_for_status()
    
    print("Waiting for extraction to complete...")
    time.sleep(2)
    # Since extraction uses EventSource/background task, we poll the job status
    while True:
        res = httpx.get(f"{API_BASE}/jobs/{job_id}/results")
        if res.status_code == 200:
            data = res.json()
            # In V2, we might not have a direct status endpoint without SSE, 
            # but we can try scoring. If extraction is not done, scoring will score what's parsed.
            break
        time.sleep(2)
        
    # Wait a bit more for background extraction to finish
    time.sleep(15) 
    
    # 6. Score
    print("\n6. Starting Scoring...")
    res = httpx.post(f"{API_BASE}/jobs/{job_id}/score", json={
        "weights": {
            "skills": 0.4,
            "experience": 0.3,
            "keywords": 0.2,
            "education": 0.1
        }
    })
    res.raise_for_status()
    print("Scoring triggered.")
    
    print("Waiting for scoring to complete...")
    time.sleep(10)
    
    # 7. Get Results
    print("\n7. Fetching Final Results...")
    res = httpx.get(f"{API_BASE}/jobs/{job_id}/results")
    if res.status_code == 200:
        results = res.json()
        candidates = results.get("candidates", [])
        print(f"Retrieved {len(candidates)} scored candidates.")
        for i, c in enumerate(candidates[:10]):
            print(f"Rank {i+1}: {c.get('name')} (Score: {c.get('overallScore')}) - Signal: {c.get('signal')}")
    else:
        print(f"Failed to get results: {res.text}")
        
    print("\n=== E2E Test Complete ===")

if __name__ == "__main__":
    main()
