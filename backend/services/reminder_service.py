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

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._check_loop())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None


reminder_service = ReminderService()
