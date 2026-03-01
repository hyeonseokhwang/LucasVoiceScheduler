import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure backend dir is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import HOST, PORT

SCHEDULER_API_KEY = os.environ.get("SCHEDULER_API_KEY")
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
from services.db_service import init_db
from services.reminder_service import reminder_service
from routers.schedule import router as schedule_router
from routers.voice import router as voice_router
from routers.challenge import router as challenge_router
from routers.briefing import router as briefing_router
from routers.stats import router as stats_router
from routers.natural import router as natural_router
from routers.template import router as template_router
from routers.dashboard import router as dashboard_router
from routers.export import router as export_router


async def _prewarm_ollama():
    """서버 시작 시 Ollama 모델을 VRAM에 미리 올림 (콜드 스타트 방지)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen2.5:14b", "prompt": "hi", "stream": False,
                      "keep_alive": "60m", "options": {"num_predict": 1}},
            )
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    reminder_service.start()
    # Daily briefing auto-generation at KST 08:00
    from services.briefing_service import briefing_scheduler
    briefing_scheduler.start()
    # Pre-load Whisper model in background thread (avoids first-request delay)
    try:
        from services.whisper_service import preload_model
        preload_model()
    except Exception:
        pass
    # Ollama 모델 프리워밍 (VRAM 미리 로딩)
    import asyncio
    asyncio.create_task(_prewarm_ollama())
    yield
    reminder_service.stop()
    briefing_scheduler.stop()


app = FastAPI(title="Lucas Scheduler", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Optional API key authentication. Skipped if SCHEDULER_API_KEY is not set."""
    if SCHEDULER_API_KEY:
        # Skip auth for health check and WebSocket
        if request.url.path not in ("/api/health",) and not request.url.path.startswith("/ws"):
            key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if key != SCHEDULER_API_KEY:
                return JSONResponse(status_code=401, content={"error": "Invalid or missing API key"})
    return await call_next(request)


app.include_router(export_router)      # before schedule_router (path priority)
app.include_router(natural_router)     # before schedule_router (path priority)
app.include_router(schedule_router)
app.include_router(voice_router)
app.include_router(challenge_router)
app.include_router(briefing_router)
app.include_router(stats_router)
app.include_router(template_router)
app.include_router(dashboard_router)


@app.get("/api/health")
async def health():
    """Enhanced health check: DB, TTS, Ollama, WebSocket status."""
    import httpx
    from services.db_service import fetch_one
    from services.notification import notification_manager

    checks = {}

    # DB check
    try:
        result = await fetch_one("SELECT 1 as ok")
        checks["db"] = {"status": "ok"} if result else {"status": "error", "detail": "query failed"}
    except Exception as e:
        checks["db"] = {"status": "error", "detail": str(e)}

    # TTS (edge-tts)
    try:
        import edge_tts  # noqa: F401
        checks["tts"] = {"status": "ok", "engine": "edge-tts"}
    except ImportError:
        checks["tts"] = {"status": "unavailable", "detail": "edge-tts not installed"}

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])[:5]]
                checks["ollama"] = {"status": "ok", "models": models}
            else:
                checks["ollama"] = {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except Exception:
        checks["ollama"] = {"status": "unavailable", "detail": "not running"}

    # WebSocket connections
    ws_ch = notification_manager.get_channel("websocket")
    ws_count = len(ws_ch._connections) if ws_ch and hasattr(ws_ch, "_connections") else 0
    checks["websocket"] = {"status": "ok", "connections": ws_count}

    # Notification channels
    checks["notifications"] = {"channels": notification_manager.channels}

    all_ok = all(c.get("status") == "ok" for c in checks.values() if isinstance(c, dict) and "status" in c)

    return {
        "status": "ok" if all_ok else "degraded",
        "service": "scheduler",
        "checks": checks,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
