import json
from datetime import datetime
from typing import Optional

from services.db_service import fetch_all, fetch_one, execute


async def list_challenges(status: Optional[str] = None):
    if status:
        rows = await fetch_all(
            "SELECT * FROM challenges WHERE status = ? ORDER BY deadline ASC",
            (status,),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM challenges WHERE status != 'cancelled' ORDER BY deadline ASC"
        )

    # Enrich each challenge with parsed milestones and progress
    for ch in rows:
        if ch.get("milestones") and isinstance(ch["milestones"], str):
            ch["milestones"] = json.loads(ch["milestones"])
        ch["progress"] = _calc_progress(ch)

    return rows


async def get_challenge(challenge_id: int):
    challenge = await fetch_one(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
    )
    if not challenge:
        return None

    # Parse milestones JSON
    if challenge.get("milestones"):
        challenge["milestones"] = json.loads(challenge["milestones"])

    # Attach earnings
    earnings = await fetch_all(
        "SELECT * FROM earnings WHERE challenge_id = ? ORDER BY date ASC",
        (challenge_id,),
    )
    challenge["earnings"] = earnings

    # Calculate progress
    challenge["progress"] = _calc_progress(challenge)

    return challenge


def _calc_progress(challenge: dict) -> dict:
    target = challenge["target_amount"]
    current = challenge["current_amount"]
    deadline = challenge["deadline"]

    # Milestone progress
    milestones = challenge.get("milestones") or []
    if isinstance(milestones, str):
        milestones = json.loads(milestones)
    total_ms = len(milestones)
    done_ms = sum(1 for m in milestones if m.get("status") == "completed")

    # Percentage: revenue-based if target > 0, otherwise milestone-based
    if target > 0:
        pct = min(round(current / target * 100, 1), 100)
    elif total_ms > 0:
        pct = round(done_ms / total_ms * 100, 1)
    else:
        pct = 0

    # D-day
    try:
        dl = datetime.strptime(deadline[:10], "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        d_day = (dl - today).days
    except ValueError:
        d_day = None

    return {
        "percentage": pct,
        "d_day": d_day,
        "milestones_total": total_ms,
        "milestones_done": done_ms,
        "remaining": max(target - current, 0) if target > 0 else total_ms - done_ms,
    }


async def create_challenge(data: dict) -> dict:
    milestones = data.get("milestones")
    if milestones and isinstance(milestones, list):
        milestones = json.dumps(milestones, ensure_ascii=False)

    row_id = await execute(
        """INSERT INTO challenges (title, description, target_amount, deadline, status, milestones)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            data["title"],
            data.get("description"),
            data.get("target_amount", 0),
            data["deadline"],
            data.get("status", "active"),
            milestones,
        ),
    )
    return await get_challenge(row_id)


async def update_challenge(challenge_id: int, data: dict) -> Optional[dict]:
    existing = await fetch_one(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
    )
    if not existing:
        return None

    milestones = data.get("milestones", existing["milestones"])
    if milestones and isinstance(milestones, list):
        milestones = json.dumps(milestones, ensure_ascii=False)

    await execute(
        """UPDATE challenges SET title=?, description=?, target_amount=?,
           deadline=?, status=?, milestones=? WHERE id=?""",
        (
            data.get("title", existing["title"]),
            data.get("description", existing["description"]),
            data.get("target_amount", existing["target_amount"]),
            data.get("deadline", existing["deadline"]),
            data.get("status", existing["status"]),
            milestones,
            challenge_id,
        ),
    )
    return await get_challenge(challenge_id)


async def add_earning(challenge_id: int, data: dict) -> dict:
    challenge = await fetch_one(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
    )
    if not challenge:
        return None

    amount = data["amount"]

    # Insert earning record
    earn_date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    earning_id = await execute(
        """INSERT INTO earnings (challenge_id, amount, source, date, note)
           VALUES (?, ?, ?, ?, ?)""",
        (
            challenge_id,
            amount,
            data.get("source"),
            earn_date,
            data.get("note"),
        ),
    )

    # Update challenge current_amount
    new_amount = challenge["current_amount"] + amount
    await execute(
        "UPDATE challenges SET current_amount = ? WHERE id = ?",
        (new_amount, challenge_id),
    )

    # Auto-complete if target reached
    if new_amount >= challenge["target_amount"] and challenge["status"] == "active":
        await execute(
            "UPDATE challenges SET status = 'completed' WHERE id = ?",
            (challenge_id,),
        )

    return await fetch_one("SELECT * FROM earnings WHERE id = ?", (earning_id,))


async def get_progress(challenge_id: int) -> Optional[dict]:
    challenge = await get_challenge(challenge_id)
    if not challenge:
        return None
    return challenge["progress"]


async def update_milestone(challenge_id: int, milestone_index: int, status: str) -> Optional[dict]:
    challenge = await fetch_one(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
    )
    if not challenge:
        return None

    milestones = json.loads(challenge["milestones"]) if challenge["milestones"] else []
    if milestone_index < 0 or milestone_index >= len(milestones):
        return None

    milestones[milestone_index]["status"] = status
    if status == "completed":
        milestones[milestone_index]["completed_at"] = datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    await execute(
        "UPDATE challenges SET milestones = ? WHERE id = ?",
        (json.dumps(milestones, ensure_ascii=False), challenge_id),
    )

    # Auto-complete challenge if all milestones done and no revenue target
    total_ms = len(milestones)
    done_ms = sum(1 for m in milestones if m.get("status") == "completed")
    if done_ms == total_ms and total_ms > 0 and challenge["target_amount"] == 0:
        await execute(
            "UPDATE challenges SET status = 'completed' WHERE id = ? AND status = 'active'",
            (challenge_id,),
        )

    return await get_challenge(challenge_id)
