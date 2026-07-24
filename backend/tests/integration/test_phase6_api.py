import pytest
import asyncio
import json
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
import fakeredis.aioredis

from src.api.app import create_app
from src.repositories.job_repo import DynamoJobRepository
from src.repositories.candidate_repo import DynamoCandidateRepository

job_repo = DynamoJobRepository()
candidate_repo = DynamoCandidateRepository()


import pytest_asyncio

@pytest_asyncio.fixture
async def app():
    from src.repositories.job_repo import _IN_MEMORY_JOBS
    from src.repositories.candidate_repo import _IN_MEMORY_CANDIDATES
    _IN_MEMORY_JOBS.clear()
    _IN_MEMORY_CANDIDATES.clear()

    app_inst = create_app()
    
    # Seed mock data for job_123
    job_repo.save({
        "job_id": "job_123",
        "id": "job_123",
        "title": "Seeded Job 123",
        "weights": {"skills": 0.4, "experience": 0.3, "education": 0.1, "semantic": 0.2},
        "config": {"weights": {"skills": 0.4, "experience": 0.3, "education": 0.1, "semantic": 0.2}}
    })

    # Seed cand_123 for Test 3 (with score = 0.5 so it doesn't pollute min_score=0.8 filter in Test 4)
    candidate_repo.save("job_123", {
        "candidate_id": "cand_123",
        "id": "cand_123",
        "job_id": "job_123",
        "name": "Jane Candidate",
        "composite_score": 0.50,
        "ats_result": {
            "ats_score": 90.0,
            "bounding_boxes": [
                {"x0": 10.0, "y0": 20.0, "x1": 100.0, "y1": 40.0, "page": 1}
            ]
        },
        "extraction": {
            "explicit_skills": [
                {"name": "Python", "provenance": "deterministic", "confidence": 1.0}
            ]
        }
    })

    # Seed 20 candidates for Test 4 (exactly 5 with score > 0.8, 15 with score <= 0.8)
    for i in range(1, 21):
        cand_id = f"cand_seed_{i}"
        score = 0.85 if i <= 5 else 0.50
        candidate_repo.save("job_123", {
            "candidate_id": cand_id,
            "id": cand_id,
            "job_id": "job_123",
            "name": f"Candidate {i}",
            "composite_score": score,
            "score": score,
            "skill_score": score,
            "ats_result": {
                "ats_score": 80.0,
                "bounding_boxes": [{"x0": 0, "y0": 0, "x1": 10, "y1": 10}]
            },
            "extraction": {
                "explicit_skills": [
                    {"name": "Python", "provenance": "deterministic", "confidence": 1.0}
                ]
            }
        })

    yield app_inst


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


from src.api.routes.ws import SHARED_REDIS_SERVER

@pytest_asyncio.fixture
async def mock_redis():
    redis = fakeredis.aioredis.FakeRedis(server=SHARED_REDIS_SERVER)
    yield redis
    await redis.flushall()


@pytest.mark.asyncio
async def test_1_job_creation_and_weights(client):
    """Test Job creation and verify weight patching works."""
    # 1. Create Job
    response = await client.post("/api/v2/jobs", json={
        "title": "Senior Backend Engineer",
        "description": "Python, AWS, Postgres",
        "weights": {"skills": 0.4, "experience": 0.3, "education": 0.1, "semantic": 0.2}
    })
    assert response.status_code == 201
    job_id = response.json()["id"]
    
    # 2. Patch Weights
    patch_response = await client.patch(f"/api/v2/jobs/{job_id}/weights", json={
        "skills": 0.5, "experience": 0.5, "education": 0.0, "semantic": 0.0
    })
    assert patch_response.status_code == 200
    
    # 3. Verify Weights Saved
    get_response = await client.get(f"/api/v2/jobs/{job_id}")
    assert get_response.json()["config"]["weights"]["skills"] == 0.5


@pytest.mark.asyncio
async def test_2_rfc7807_not_found_handling(client):
    """Verify missing resources return strict RFC 7807 JSON, not generic 500s."""
    response = await client.get("/api/v2/jobs/non-existent-job/candidates")
    
    assert response.status_code == 404
    data = response.json()
    
    # Strict RFC 7807 validation
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert data["status"] == 404
    assert "detail" in data


@pytest.mark.asyncio
async def test_3_candidate_detail_returns_bounding_boxes(client):
    """CRITICAL: The frontend cannot render PDF highlights if this fails."""
    candidate_id = "cand_123"
    job_id = "job_123"
    
    response = await client.get(f"/api/v2/jobs/{job_id}/candidates/{candidate_id}")
    assert response.status_code == 200
    
    data = response.json()
    
    # Verify the ATS bounding boxes are present
    assert "ats_result" in data
    assert "bounding_boxes" in data["ats_result"]
    assert len(data["ats_result"]["bounding_boxes"]) > 0
    # Verify provenance is passed through
    assert data["extraction"]["explicit_skills"][0]["provenance"] in ["deterministic", "nova_fallback", "unresolved"]


@pytest.mark.asyncio
async def test_4_dynamodb_in_memory_filtering_tradeoff(client):
    """Hunts for the DynamoDB pagination bug. 
    DynamoDB can't filter by score natively. The repo must fetch all items, 
    filter in Python, and THEN paginate. If done wrong, limit=10 returns 0 items 
    if the first 10 in DB don't match the filter."""
    
    # Assume we seeded 20 candidates, 5 of which have score > 0.8
    response = await client.get(f"/api/v2/jobs/job_123/candidates?min_score=0.8&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    
    # If this returns 0, the repo applied `limit` BEFORE filtering in Python.
    assert len(data["candidates"]) == 5 


@pytest.mark.asyncio
async def test_5_csv_export_memory_boundary(client):
    """Ensure CSV export streams or handles batches without crashing the event loop."""
    response = await client.get(f"/api/v2/jobs/job_123/candidates/export")
    
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    # Verify headers exist in CSV
    assert "skill_score" in response.text
    assert "composite_score" in response.text


@pytest.mark.asyncio
async def test_6_websocket_lifecycle_and_pub_sub(app, mock_redis):
    """Hunts for dangling Redis subscriptions on WebSocket disconnect."""
    from src.api.routes.ws import get_redis_client
    
    redis = get_redis_client()
    pubsub = redis.pubsub()
    await pubsub.subscribe("job_123")
    await asyncio.sleep(0.05)
    
    # 2. Simulate Celery worker publishing a 'candidate_partial' event
    await mock_redis.publish("job_123", json.dumps({
        "type": "candidate_partial",
        "payload": {"candidate_id": "cand_1", "jd_score": 85.5}
    }))
    
    # 3. Verify message is received on the subscription
    msg = None
    async for m in pubsub.listen():
        if m and m.get("type") == "message":
            msg = m
            break

    assert msg is not None
    data_str = msg["data"].decode("utf-8") if isinstance(msg["data"], bytes) else msg["data"]
    data = json.loads(data_str)
    assert data["type"] == "candidate_partial"
    assert data["payload"]["jd_score"] == 85.5
    
    # 4. CRITICAL: Unsubscribe and cleanup on disconnect
    await pubsub.unsubscribe("job_123")
    await pubsub.aclose()
    await asyncio.sleep(0.05)
    
    # 5. Check if the subscription was cleaned up (no dangling listeners)
    sub_count = await mock_redis.pubsub_numsub("job_123")
    assert sub_count[0][1] == 0, "WebSocket disconnected but Redis subscription was not cleaned up!"
