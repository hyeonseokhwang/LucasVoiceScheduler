from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "scheduler.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"

HOST = "0.0.0.0"
PORT = 7778  # 리부트 후 7778 복구 완료

REMINDER_CHECK_INTERVAL = 30  # seconds
