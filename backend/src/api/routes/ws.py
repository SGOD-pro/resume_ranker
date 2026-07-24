import json
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import fakeredis
import fakeredis.aioredis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSockets"])

# Shared FakeServer for in-memory Redis Pub/Sub in local dev and testing
SHARED_REDIS_SERVER = fakeredis.FakeServer()

def get_redis_client():
    return fakeredis.aioredis.FakeRedis(server=SHARED_REDIS_SERVER)

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

manager = ConnectionManager()

@router.websocket("/ws/jobs/{job_id}")
async def websocket_job_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint supporting Redis Pub/Sub for job events:
    candidate_partial, candidate_ready, candidate_failed, processing_complete.
    Ensures complete unsubscription and cleanup on disconnect to avoid memory leaks.
    """
    await manager.connect(job_id, websocket)
    redis = get_redis_client()
    pubsub = redis.pubsub()
    
    try:
        await pubsub.subscribe(job_id)
        
        async def listen_redis():
            try:
                async for message in pubsub.listen():
                    if message and message.get("type") == "message":
                        data_str = message.get("data")
                        if isinstance(data_str, bytes):
                            data_str = data_str.decode("utf-8")
                        try:
                            payload = json.loads(data_str)
                            await websocket.send_json(payload)
                        except Exception:
                            await websocket.send_text(data_str)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("Redis listener error: %s", e)

        listen_task = asyncio.create_task(listen_redis())

        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"event": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            listen_task.cancel()
            await asyncio.gather(listen_task, return_exceptions=True)
            
    finally:
        manager.disconnect(job_id, websocket)
        try:
            await pubsub.unsubscribe(job_id)
            await pubsub.aclose()
            await redis.aclose()
        except Exception as e:
            logger.warning("Error during Pub/Sub cleanup: %s", e)
