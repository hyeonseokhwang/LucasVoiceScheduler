import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure backend dir is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import HOST, PORT
from services.db_service import init_db
from services.reminder_service import reminder_service
from routers.schedule import router as schedule_router
from routers.voice import router as voice_router
from routers.challenge import router as challenge_router


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


app = FastAPI(title="Lucas Scheduler", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedule_router)
app.include_router(voice_router)
app.include_router(challenge_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "scheduler"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
