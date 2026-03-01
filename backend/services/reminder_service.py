import asyncio
import json
from datetime import datetime
from fastapi import WebSocket
from config import REMINDER_CHECK_INTERVAL
from services.schedule_service import get_due_reminders


class ReminderService:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._task: asyncio.Task | None = None
        self._challenge_task: asyncio.Task | None = None
        self._notified_challenges: set[str] = set()  # track sent notifications

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def _check_loop(self):
        while True:
            try:
                reminders = await get_due_reminders()
                for r in reminders:
                    await self.broadcast({
                        "type": "reminder",
                        "schedule": r,
                    })
            except Exception as e:
                print(f"[ReminderService] Error: {e}")
            await asyncio.sleep(REMINDER_CHECK_INTERVAL)

    async def _challenge_check_loop(self):
        """챌린지 D-day 및 마일스톤 기한 알림 (매 5분 체크)."""
        while True:
            try:
                await self._check_challenge_reminders()
            except Exception as e:
                print(f"[ReminderService] Challenge check error: {e}")
            await asyncio.sleep(300)  # 5분 간격

    async def _check_challenge_reminders(self):
        from services.db_service import fetch_all

        today = datetime.now().strftime("%Y-%m-%d")
        challenges = await fetch_all(
            "SELECT * FROM challenges WHERE status = 'active'"
        )

        for ch in challenges:
            deadline = ch["deadline"][:10]
            try:
                dl = datetime.strptime(deadline, "%Y-%m-%d")
                now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                d_day = (dl - now).days
            except ValueError:
                continue

            # D-7, D-3, D-day alerts
            for threshold in [7, 3, 0]:
                if d_day == threshold:
                    key = f"challenge-{ch['id']}-d{threshold}-{today}"
                    if key not in self._notified_challenges:
                        self._notified_challenges.add(key)
                        if threshold == 0:
                            msg = f"'{ch['title']}' 챌린지 마감일입니다! 현재 {ch['current_amount']:,}원 달성."
                        else:
                            msg = f"'{ch['title']}' 챌린지 마감 D-{threshold}! 현재 {ch['current_amount']:,}원 / 목표 {ch['target_amount']:,}원."
                        await self.broadcast({
                            "type": "challenge_reminder",
                            "challenge_id": ch["id"],
                            "title": ch["title"],
                            "d_day": d_day,
                            "message": msg,
                        })

            # Milestone deadline alerts
            milestones = json.loads(ch["milestones"]) if ch.get("milestones") else []
            for i, ms in enumerate(milestones):
                if ms.get("status") == "completed":
                    continue
                ms_date = ms.get("due_date", "")[:10]
                try:
                    ms_dl = datetime.strptime(ms_date, "%Y-%m-%d")
                    ms_days = (ms_dl - now).days
                except ValueError:
                    continue

                if ms_days in [3, 0]:
                    key = f"milestone-{ch['id']}-{i}-d{ms_days}-{today}"
                    if key not in self._notified_challenges:
                        self._notified_challenges.add(key)
                        if ms_days == 0:
                            msg = f"마일스톤 '{ms['title']}' 기한이 오늘입니다!"
                        else:
                            msg = f"마일스톤 '{ms['title']}' 기한까지 {ms_days}일 남았습니다."
                        await self.broadcast({
                            "type": "milestone_reminder",
                            "challenge_id": ch["id"],
                            "milestone_index": i,
                            "milestone_title": ms["title"],
                            "d_day": ms_days,
                            "message": msg,
                        })

        # Clean old notification keys (keep only today's)
        self._notified_challenges = {k for k in self._notified_challenges if k.endswith(today)}

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._check_loop())
        if self._challenge_task is None:
            self._challenge_task = asyncio.create_task(self._challenge_check_loop())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
        if self._challenge_task:
            self._challenge_task.cancel()
            self._challenge_task = None


reminder_service = ReminderService()
