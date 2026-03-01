"""Schedule template service.

Manages reusable schedule templates (e.g., weekly routine, exercise schedule).
Templates are stored in the `schedule_templates` table.
"""

import json
from typing import Optional

from services.db_service import fetch_all, fetch_one, execute


async def ensure_table():
    """Create template table if not exists."""
    await execute("""
        CREATE TABLE IF NOT EXISTS schedule_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            template_data TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            usage_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)


async def list_templates(category: Optional[str] = None) -> list[dict]:
    """List all templates, optionally filtered by category."""
    await ensure_table()
    if category:
        rows = await fetch_all(
            "SELECT * FROM schedule_templates WHERE category = ? ORDER BY usage_count DESC",
            (category,),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM schedule_templates ORDER BY usage_count DESC"
        )
    for r in rows:
        if r.get("template_data") and isinstance(r["template_data"], str):
            r["template_data"] = json.loads(r["template_data"])
    return rows


async def get_template(template_id: int) -> Optional[dict]:
    """Get a template by ID."""
    await ensure_table()
    row = await fetch_one(
        "SELECT * FROM schedule_templates WHERE id = ?", (template_id,)
    )
    if row and isinstance(row.get("template_data"), str):
        row["template_data"] = json.loads(row["template_data"])
    return row


async def create_template(data: dict) -> dict:
    """Create a new schedule template."""
    await ensure_table()
    template_data = data.get("template_data", {})
    if isinstance(template_data, dict):
        template_data = json.dumps(template_data)

    row_id = await execute(
        """INSERT INTO schedule_templates (name, description, template_data, category)
           VALUES (?, ?, ?, ?)""",
        (
            data["name"],
            data.get("description"),
            template_data,
            data.get("category", "general"),
        ),
    )
    return await get_template(row_id)


async def update_template(template_id: int, data: dict) -> Optional[dict]:
    """Update an existing template."""
    await ensure_table()
    existing = await get_template(template_id)
    if not existing:
        return None

    template_data = data.get("template_data", existing["template_data"])
    if isinstance(template_data, dict):
        template_data = json.dumps(template_data)

    await execute(
        """UPDATE schedule_templates
           SET name=?, description=?, template_data=?, category=?, updated_at=datetime('now')
           WHERE id=?""",
        (
            data.get("name", existing["name"]),
            data.get("description", existing.get("description")),
            template_data,
            data.get("category", existing["category"]),
            template_id,
        ),
    )
    return await get_template(template_id)


async def delete_template(template_id: int) -> bool:
    """Delete a template."""
    await ensure_table()
    from services.db_service import execute_returning
    _, rowcount = await execute_returning(
        "DELETE FROM schedule_templates WHERE id = ?", (template_id,)
    )
    return rowcount > 0


async def apply_template(template_id: int, start_date: str) -> list[dict]:
    """Apply a template to create schedules starting from the given date.

    The template_data should contain a list of schedule items with relative
    time offsets, or a single schedule item.
    """
    from datetime import datetime, timedelta
    from services import schedule_service

    await ensure_table()
    template = await get_template(template_id)
    if not template:
        return []

    td = template["template_data"]
    items = td if isinstance(td, list) else [td]

    try:
        base_date = datetime.strptime(start_date[:10], "%Y-%m-%d")
    except ValueError:
        base_date = datetime.now()

    created = []
    for item in items:
        schedule_data = dict(item)
        # If start_at is a time-only string like "09:00", combine with base_date
        start_at = schedule_data.get("start_at", "09:00:00")
        if len(start_at) <= 8:  # Time only
            schedule_data["start_at"] = f"{base_date.strftime('%Y-%m-%d')}T{start_at}"
        if schedule_data.get("end_at") and len(schedule_data["end_at"]) <= 8:
            schedule_data["end_at"] = f"{base_date.strftime('%Y-%m-%d')}T{schedule_data['end_at']}"

        # Day offset support
        day_offset = schedule_data.pop("_day_offset", 0)
        if day_offset:
            offset_date = base_date + timedelta(days=day_offset)
            schedule_data["start_at"] = schedule_data["start_at"].replace(
                base_date.strftime("%Y-%m-%d"), offset_date.strftime("%Y-%m-%d")
            )
            if schedule_data.get("end_at"):
                schedule_data["end_at"] = schedule_data["end_at"].replace(
                    base_date.strftime("%Y-%m-%d"), offset_date.strftime("%Y-%m-%d")
                )

        result = await schedule_service.create_schedule(schedule_data)
        created.append(result)

    # Increment usage count
    await execute(
        "UPDATE schedule_templates SET usage_count = usage_count + 1 WHERE id = ?",
        (template_id,),
    )

    return created
