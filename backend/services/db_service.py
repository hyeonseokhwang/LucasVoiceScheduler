import aiosqlite
from config import DB_PATH, SCHEMA_PATH


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        await db.executescript(schema)
        await db.commit()
    finally:
        await db.close()


async def fetch_all(query: str, params: tuple = ()):
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def fetch_one(query: str, params: tuple = ()):
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def execute(query: str, params: tuple = ()):
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def execute_returning(query: str, params: tuple = ()):
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.lastrowid, cursor.rowcount
    finally:
        await db.close()
