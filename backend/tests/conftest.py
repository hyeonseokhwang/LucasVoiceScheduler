"""Shared test fixtures for Scheduler backend tests."""

import os
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Unset API key for tests
os.environ.pop("SCHEDULER_API_KEY", None)


@pytest_asyncio.fixture
async def client(tmp_path):
    """Async test client using a temporary DB file."""
    import config

    # Use a temp DB for test isolation
    test_db = tmp_path / "test_scheduler.db"
    original_db = config.DB_PATH
    config.DB_PATH = test_db

    from services.db_service import init_db
    await init_db()

    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    config.DB_PATH = original_db
