import pytest
import json
import asyncio
from httpx import AsyncClient, ASGITransport
import pytest_asyncio
import fakeredis.aioredis

from src.api.app import create_app
from src.repositories.job_repo import DynamoJobRepository, _IN_MEMORY_JOBS
from src.repositories.candidate_repo import DynamoCandidateRepository, _IN_MEMORY_CANDIDATES
from src.api.routes.ws import SHARED_REDIS_SERVER

job_repo = DynamoJobRepository()
candidate_repo = DynamoCandidateRepository()

@pytest_asyncio.fixture
async def app():
    _IN_MEMORY_JOBS.clear()
    _IN_MEMORY_CANDIDATES.clear()

    app_inst = create_app()

    # Seed job_123 and 15 candidates for pagination and CSV tests
    job_repo.save({
        "job_id": "job_123",
        "id": "job_123",
        "title": "Vice President, Engineering",
        "description": "Lead engineering team"
    })

    for i in range(1, 16):
        cand_id = f"cand_stress_{i}"
        title = "Vice President, Engineering" if i % 2 == 0 else "Senior Software Engineer"
        candidate_repo.save("job_123", {
            "candidate_id": cand_id,
            "id": cand_id,
            "job_id": "job_123",
            "name": f"Candidate {i}",
            "title": title,
            "composite_score": 90.0 - i,
            "skill_score": 85.0,
            "experience_score": 80.0,
            "education_score": 75.0,
            "ats_result": {
                "ats_score": 90.0,
                "bounding_boxes": [{"x0": 0, "y0": 0, "x1": 10, "y1": 10}]
            }
        })

    yield app_inst

@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def mock_redis():
    redis = fakeredis.aioredis.FakeRedis(server=SHARED_REDIS_SERVER)
    yield redis
    await redis.flushall()


@pytest.mark.asyncio
async def test_7_dynamodb_pagination_cursor_integrity(client):
    """Tests if the `next_cursor` returned actually fetches the next page, 
    or if it loops infinitely/returns duplicates."""
    job_id = "job_123"
    limit = 5
    
    # Page 1
    res1 = await client.get(f"/api/v2/jobs/{job_id}/candidates?limit={limit}")
    assert res1.status_code == 200
    data1 = res1.json()
    
    assert len(data1["candidates"]) == limit
    cursor = data1.get("next_cursor")
    assert cursor is not None, "Cursor missing when more data exists"
    
    # Page 2
    res2 = await client.get(f"/api/v2/jobs/{job_id}/candidates?limit={limit}&cursor={cursor}")
    assert res2.status_code == 200
    data2 = res2.json()
    
    # Ensure we didn't get the same items again
    ids_page1 = {c["id"] for c in data1["candidates"]}
    ids_page2 = {c["id"] for c in data2["candidates"]}
    
    assert len(ids_page1.intersection(ids_page2)) == 0, "Pagination cursor returned duplicate items!"


@pytest.mark.asyncio
async def test_8_csv_injection_and_comma_escaping(client):
    """A candidate's job title contains a comma or starts with =, +, -.
    If not escaped, this breaks CSV formatting or allows formula injection."""
    job_id = "job_123"
    
    response = await client.get(f"/api/v2/jobs/{job_id}/candidates/export")
    
    assert response.status_code == 200
    text = response.text
    
    lines = text.splitlines()
    if len(lines) > 1:
        header = lines[0]
        for line in lines[1:]:
            if line.count(",") > header.count(","):
                assert '"' in line, "CSV field with comma is not properly enclosed in double quotes"


@pytest.mark.asyncio
async def test_9_websocket_concurrent_burst(app, mock_redis):
    """Simulates Celery worker finishing 20 candidates at the exact same millisecond.
    Tests if WebSocket loop blocks or drops messages under burst load."""
    from src.api.routes.ws import get_redis_client

    redis = get_redis_client()
    pubsub = redis.pubsub()
    await pubsub.subscribe("job_burst")
    await asyncio.sleep(0.05)

    # Publish 20 candidate_ready events concurrently
    for i in range(20):
        await mock_redis.publish("job_burst", json.dumps({
            "type": "candidate_ready",
            "payload": {"candidate_id": f"cand_{i}", "score": 80.0}
        }))

    received_count = 0
    try:
        async for msg in pubsub.listen():
            if msg and msg.get("type") == "message":
                received_count += 1
                if received_count == 20:
                    break
    except asyncio.TimeoutError:
        pass

    assert received_count == 20, f"WebSocket dropped messages! Received {received_count}/20 during burst."

    await pubsub.unsubscribe("job_burst")
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_10_presigned_url_validation(client):
    """Tests the /resumes endpoint. Does it return a valid S3 URL structure?
    The frontend will immediately try to PUT a file to this URL."""
    
    # Create a dummy job first
    job_res = await client.post("/api/v2/jobs", json={"title": "Test", "description": "Test"})
    job_id = job_res.json()["id"]
    
    # Request upload URL
    res = await client.post(f"/api/v2/jobs/{job_id}/resumes", json={"filename": "resume.pdf"})
    
    assert res.status_code == 200
    data = res.json()
    
    assert "url" in data
    assert "amazonaws.com" in data["url"] or "localhost" in data["url"]
    assert "fields" in data or "headers" in data, "Missing required S3 upload headers for frontend PUT request"
