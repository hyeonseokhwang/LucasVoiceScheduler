import asyncio
import json
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from fastapi import WebSocket
from config import REMINDER_CHECK_INTERVAL
from services.schedule_service import get_due_reminders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TTS_VOICE = "ko-KR-SunHiNeural"
TTS_ENABLED = True


class ReminderService:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._task: asyncio.Task | None = None
        self._challenge_task: asyncio.Task | None = None
        self._notified_challenges: set[str] = set()
        self._notified_reminders: set[str] = set()  # prevent duplicate schedule reminders

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
                    # Prevent duplicate notifications
                    key = f"sched-{r['id']}-{r.get('remind_at', '')}"
                    if key in self._notified_reminders:
                        continue
                    self._notified_reminders.add(key)

                    # Build human-readable message
                    try:
                        start_dt = datetime.strptime(r["start_at"][:16], "%Y-%m-%dT%H:%M")
                        time_str = start_dt.strftime("%H시 %M분") if start_dt.minute else start_dt.strftime("%H시")
                    except Exception:
                        time_str = r["start_at"]
                    message = f"10분 후 '{r['title']}' 일정이 시작됩니다. ({time_str})"

                    await self.broadcast({
                        "type": "reminder",
                        "schedule": r,
                        "message": message,
                    })
                    logger.info(f"[Reminder] {message}")

                    # Generate TTS audio
                    if TTS_ENABLED:
                        asyncio.create_task(self._generate_tts(message, r["id"]))

                # Clean old reminder keys (keep last 200)
                if len(self._notified_reminders) > 200:
                    self._notified_reminders = set(list(self._notified_reminders)[-100:])

            except Exception as e:
                logger.error(f"[ReminderService] Error: {e}")
            await asyncio.sleep(REMINDER_CHECK_INTERVAL)

    async def _generate_tts(self, text: str, schedule_id: int):
        """Generate TTS audio file using Edge TTS for voice reminder."""
        try:
            tts_dir = Path(__file__).resolve().parent.parent / "tts_cache"
            tts_dir.mkdir(exist_ok=True)
            output_path = tts_dir / f"reminder_{schedule_id}.mp3"

            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "edge_tts",
                "--voice", TTS_VOICE,
                "--text", text,
                "--write-media", str(output_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=15)

            if output_path.exists():
                logger.info(f"[TTS] Generated: {output_path} ({output_path.stat().st_size} bytes)")
                # Broadcast TTS availability
                await self.broadcast({
                    "type": "tts_ready",
                    "schedule_id": schedule_id,
                    "audio_url": f"/api/voice/reminder/{schedule_id}",
                })
        except Exception as e:
            logger.warning(f"[TTS] Generation failed: {e}")

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
