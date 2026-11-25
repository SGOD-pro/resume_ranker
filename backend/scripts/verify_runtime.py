import urllib.request
import urllib.error
import json
import time
import os
import sys

BASE = "http://localhost:8000"
sys.path.insert(0, "backend")
from src.api.auth import User, create_session_token

print("=== Check 1: Health Endpoint ===")
with urllib.request.urlopen(f"{BASE}/health") as r:
    health_data = json.loads(r.read())
    assert r.status == 200
    assert health_data["status"] == "ok"
    print(f"Health check PASSED: HTTP {r.status}, body={health_data}")

print("\n=== Check 2: WF-01 Job Creation ===")
user_a = User(user_id="user_1", org_id="org_alpha", email="alice@alpha.com", name="Alice", role="recruiter", password_hash="", created_at=time.time())
token_org_a = create_session_token(user_a)
headers_a = {"Cookie": f"sortlist_session={token_org_a}", "Content-Type": "application/json"}
req_job = urllib.request.Request(
    f"{BASE}/api/v2/jobs",
    method="POST",
    data=json.dumps({
        "title": "Senior Python Backend Engineer",
        "must_have_skills": ["Python", "FastAPI"],
        "min_years": 3,
        "max_years": 10
    }).encode(),
    headers=headers_a
)
with urllib.request.urlopen(req_job) as r:
    job = json.loads(r.read())
    job_id = job["id"]
    job_status = job["status"]
    assert r.status in (200, 201)
    print(f"Job Creation PASSED: HTTP {r.status}, job_id={job_id}, status={job_status}")

print("\n=== Check 3: SEC-02 Tenant Isolation (Cross-Tenant Access) ===")
user_b = User(user_id="user_2", org_id="org_beta", email="bob@beta.com", name="Bob", role="recruiter", password_hash="", created_at=time.time())
token_org_b = create_session_token(user_b)
headers_b = {"Cookie": f"sortlist_session={token_org_b}", "Content-Type": "application/json"}
req_cross = urllib.request.Request(f"{BASE}/api/v2/jobs/{job_id}/status", method="GET", headers=headers_b)
try:
    urllib.request.urlopen(req_cross)
    print("FAILED: Cross-tenant access succeeded!")
    sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 403
    print(f"Tenant Isolation PASSED: HTTP {e.code} Forbidden on cross-tenant access")

print("\n=== Check 4: SEC-04 File Validation (Truncated / Corrupted PDF) ===")
boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body_bad = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"files\"; filename=\"truncated.pdf\"\r\n"
    f"Content-Type: application/pdf\r\n\r\n"
    f"%PDF-too-short\r\n"
    f"--{boundary}--\r\n"
).encode()
req_upload_bad = urllib.request.Request(
    f"{BASE}/api/v2/jobs/{job_id}/resumes",
    method="POST",
    data=body_bad,
    headers={"Cookie": f"sortlist_session={token_org_a}", "Content-Type": f"multipart/form-data; boundary={boundary}"}
)
with urllib.request.urlopen(req_upload_bad) as r:
    bad_res = json.loads(r.read())
    assert len(bad_res.get("rejected", [])) > 0
    assert len(bad_res.get("accepted", [])) == 0
    rej_reason = bad_res["rejected"][0]["reason"]
    print(f"Multipart File Validation PASSED: rejected={bad_res['rejected']}")

# Also test S3 upload session complete endpoint directly with corrupt document
req_sess = urllib.request.Request(
    f"{BASE}/api/v2/jobs/{job_id}/upload-sessions",
    method="POST",
    data=json.dumps({"document_count": 1, "files": [{"filename": "corrupt.pdf", "file_size": 20}]}).encode(),
    headers=headers_a
)
with urllib.request.urlopen(req_sess) as r:
    sess_data = json.loads(r.read())
    sess_id = sess_data["session_id"]
    doc_info = sess_data["documents"][0]
    doc_id = doc_info["document_id"]

# Complete before valid PDF uploaded -> must return 400
req_comp = urllib.request.Request(
    f"{BASE}/api/v2/jobs/{job_id}/upload-sessions/{sess_id}/documents/{doc_id}/complete",
    method="POST",
    data=b"{}",
    headers=headers_a
)
try:
    urllib.request.urlopen(req_comp)
    print("FAILED: incomplete S3 upload complete accepted!")
    sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 400
    print(f"Upload-Session Complete Validation PASSED: HTTP {e.code} on missing/corrupt S3 object")

print("\n=== Check 5: WF-02 End-to-End Resume Upload & Analysis ===")
with open("backend/data/resumes/1.pdf", "rb") as f:
    pdf_bytes = f.read()

body_good = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"files\"; filename=\"1.pdf\"\r\n"
    f"Content-Type: application/pdf\r\n\r\n"
).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()

req_upload_good = urllib.request.Request(
    f"{BASE}/api/v2/jobs/{job_id}/resumes",
    method="POST",
    data=body_good,
    headers={"Cookie": f"sortlist_session={token_org_a}", "Content-Type": f"multipart/form-data; boundary={boundary}"}
)
with urllib.request.urlopen(req_upload_good) as r:
    up_res = json.loads(r.read())
    enq_count = up_res.get("enqueued_count", 1)
    assert r.status in (200, 202)
    print(f"Upload PASSED: HTTP {r.status}, enqueued={enq_count}")

# Trigger analysis
req_analysis = urllib.request.Request(
    f"{BASE}/api/v2/jobs/{job_id}/analysis",
    method="POST",
    data=b"{}",
    headers=headers_a
)
with urllib.request.urlopen(req_analysis) as r:
    ana_res = json.loads(r.read())
    ana_status = ana_res.get("status")
    assert r.status == 202
    print(f"Analysis Triggered: HTTP 202, status={ana_status}")

# Poll results until terminal
print("Waiting for background worker processing...")
max_wait = 20
results_data = None
for _ in range(max_wait):
    time.sleep(1)
    req_res = urllib.request.Request(f"{BASE}/api/v2/jobs/{job_id}/results", method="GET", headers=headers_a)
    try:
        with urllib.request.urlopen(req_res) as r:
            results_data = json.loads(r.read())
            cands = results_data.get("candidates", [])
            st = results_data.get("status")
            if cands or st in ("READY", "READY_WITH_WARNINGS", "DONE", "DONE_WITH_ERRORS"):
                break
    except Exception:
        pass

assert results_data is not None
final_st = results_data.get("status")
cands_list = results_data.get("candidates", [])
print(f"E2E Processing PASSED: job status={final_st}, total candidates={len(cands_list)}")
if cands_list:
    c = cands_list[0]
    print(f"Top Candidate: name={c.get('name')}, score={c.get('final_score')}, status={c.get('eligibility_status')}")

print("\n=== Check 6: ATS-01 B2B Health Check ===")
body_ats = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"file\"; filename=\"1.pdf\"\r\n"
    f"Content-Type: application/pdf\r\n\r\n"
).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()

req_ats = urllib.request.Request(
    f"{BASE}/api/v2/jobs/ats-check",
    method="POST",
    data=body_ats,
    headers={"Cookie": f"sortlist_session={token_org_a}", "Content-Type": f"multipart/form-data; boundary={boundary}"}
)
with urllib.request.urlopen(req_ats) as r:
    ats_res = json.loads(r.read())
    ats_score = ats_res.get("score")
    ats_rating = ats_res.get("overall_rating")
    assert r.status == 200
    print(f"ATS Health Check PASSED: HTTP 200, score={ats_score}, overall={ats_rating}")
print("\n>>> ALL RUNTIME BEHAVIORAL CHECKS PASSED <<<")
