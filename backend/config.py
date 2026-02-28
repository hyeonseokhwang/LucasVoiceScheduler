from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "scheduler.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"

HOST = "0.0.0.0"
PORT = 7779  # 7778 유령 소켓 점유 중 → 임시 7779

REMINDER_CHECK_INTERVAL = 30  # seconds
