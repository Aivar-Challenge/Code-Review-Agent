"""
FastAPI main application entry point.
Includes REST API routes, WebSocket log streaming, and CORS.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.db.database import init_db
from backend.api.review import router as review_router, get_log_queues_store, get_run_logs_store
from backend.api.runs import router as runs_router
from backend.api.config import router as config_router

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("🔧 Initializing database...")
    await init_db()
    logger.info("✅ Database ready")
    yield
    logger.info("👋 Shutting down")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Code Review Agent",
    description="AI-powered GitHub PR code review agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ────────────────────────────────────────────────────────────────
app.include_router(review_router)
app.include_router(runs_router)
app.include_router(config_router)


# ── WebSocket Log Streaming ───────────────────────────────────────────────────
@app.websocket("/ws/logs/{run_id}")
async def websocket_logs(websocket: WebSocket, run_id: str):
    """
    Stream live log messages for a review run.
    Sends existing logs immediately, then streams new ones as they arrive.
    """
    await websocket.accept()
    log_queues = get_log_queues_store()
    logs_store = get_run_logs_store()

    try:
        # Send existing logs first
        existing = logs_store.get(run_id, [])
        for entry in existing:
            await websocket.send_text(json.dumps(entry))

        # Create a queue for live updates
        q: asyncio.Queue = asyncio.Queue()
        log_queues.setdefault(run_id, []).append(q)

        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=30.0)
                    await websocket.send_text(json.dumps(entry))
                    if entry.get("message") == "__DONE__":
                        break
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await websocket.send_text(json.dumps({"message": "__PING__", "level": "system"}))

        finally:
            if q in log_queues.get(run_id, []):
                log_queues[run_id].remove(q)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for run {run_id}")
    except Exception as e:
        logger.error(f"WebSocket error for run {run_id}: {e}")


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "code-review-agent"}


# ── Serve Frontend ────────────────────────────────────────────────────────────
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        index = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index)


if __name__ == "__main__":
    import uvicorn
    from backend.config import settings
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
