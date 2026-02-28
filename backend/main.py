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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "scheduler"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
