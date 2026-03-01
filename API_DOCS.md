# Lucas Scheduler API Documentation

Base URL: `http://localhost:7778`

## Authentication

Optional API key authentication via `SCHEDULER_API_KEY` environment variable.
When set, all requests (except `/api/health` and WebSocket) require:
- Header: `X-API-Key: <key>`
- Or query param: `?api_key=<key>`

When unset, all requests pass through without authentication.

## Rate Limiting

60 requests per minute per IP address (via slowapi).

---

## Schedules (8 endpoints)

### GET /api/schedules
List schedules with optional filters.

| Param | Type | Description |
|-------|------|-------------|
| from | string | Start date filter (ISO 8601) |
| to | string | End date filter (ISO 8601) |
| status | string | Filter by status (active/completed/cancelled) |
| category | string | Filter by category |

### POST /api/schedules
Create a new schedule. `remind_at` auto-set to `start_at - 10 minutes` if not provided.

```json
{
  "title": "Meeting",
  "start_at": "2026-03-10T10:00:00",
  "end_at": "2026-03-10T11:00:00",
  "category": "meeting",
  "description": "Optional",
  "all_day": false,
  "remind_at": "2026-03-10T09:50:00",
  "recurrence": {"freq": "weekly", "interval": 1, "days": [0,2,4]}
}
```

### GET /api/schedules/{id}
Get a single schedule by ID.

### PUT /api/schedules/{id}
Update a schedule. Partial update supported.

### DELETE /api/schedules/{id}
Soft-delete (sets status to `cancelled`).

### POST /api/schedules/{id}/complete
Mark schedule as completed.

### GET /api/schedules/upcoming
Get upcoming schedules (default: next 24 hours).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| hours | int | 24 | Hours to look ahead |

### GET /api/schedules/calendar/{year}/{month}
Get all schedules for a calendar month (expands recurring).

### GET /api/schedules/search
Search schedules by title or description.

| Param | Type | Description |
|-------|------|-------------|
| q | string | Search query |
| limit | int | Max results (default 20) |

---

## Challenges (7 endpoints)

### GET /api/challenges
List all active challenges with progress data.

Response includes `progress` object:
```json
{
  "percentage": 25.0,
  "d_day": 121,
  "milestones_total": 4,
  "milestones_done": 1,
  "remaining": 3
}
```

### POST /api/challenges
Create a new challenge.

```json
{
  "title": "Revenue Challenge",
  "description": "Target 100K in 2 months",
  "target_amount": 100000,
  "deadline": "2026-04-30",
  "milestones": [
    {"title": "MVP Launch", "due_date": "2026-03-31", "status": "pending"}
  ]
}
```

### GET /api/challenges/{id}
Get challenge with earnings history and progress.

### PUT /api/challenges/{id}
Update challenge details.

### POST /api/challenges/{id}/earning
Record a new earning.

```json
{
  "amount": 5000,
  "source": "App Store",
  "note": "First sale",
  "date": "2026-03-15"
}
```

### PUT /api/challenges/{id}/milestone/{index}
Update milestone status. Auto-completes challenge when all milestones done (for non-revenue challenges).

```json
{"status": "completed"}
```

### GET /api/challenges/{id}/progress
Get progress calculation only.

---

## Briefing (4 endpoints)

### GET /api/briefing/today
Get today's briefing (generates if not cached). Includes weather, schedules, challenge D-day.

### GET /api/briefing/today/voice
Get today's briefing as MP3 audio (Edge TTS, ko-KR-SunHiNeural voice).
Response: `audio/mpeg`

### GET /api/briefing/{date}
Get briefing for a specific date.

### GET /api/briefing
List recent briefings.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 7 | Number of briefings |

---

## Voice Assistant (7 endpoints)

### POST /api/voice/transcribe
Transcribe audio to text (Whisper large-v3, CUDA).
Content-Type: `multipart/form-data` with `audio` file.

### POST /api/voice/parse
Parse natural language into schedule commands.

### POST /api/voice/chat
AI conversation with schedule context (Ollama qwen2.5:14b).

### POST /api/voice/chat/stream
Streaming version of chat endpoint.

### POST /api/voice/confirm
Confirm a parsed voice command.

### POST /api/voice/tts
Text-to-speech conversion. Response: `audio/mpeg` stream.

### GET /api/voice/reminder/{schedule_id}
Get TTS audio for a specific reminder. Response: `audio/mpeg`.

### GET /api/voice/context
Get current voice assistant context.

### GET /api/voice/status
Check voice service status (Whisper model, Ollama availability).

---

## System (3 endpoints)

### GET /api/health
Health check. Always returns `{"status": "ok", "service": "scheduler"}`.

### GET /api/stats/summary
Dashboard summary for Mobile Commander integration.

```json
{
  "total_schedules": 12,
  "today_schedules": 2,
  "active_challenges": 4,
  "completed_milestones": 2,
  "total_milestones": 18,
  "date": "2026-03-01"
}
```

### WS /ws
WebSocket for real-time notifications.

Message types:
- `reminder`: Schedule reminder (10 min before start)
- `tts_ready`: TTS audio generated for a reminder
- `challenge_reminder`: Challenge D-day alerts (D-7, D-3, D-Day)
- `milestone_reminder`: Milestone deadline alerts (D-3, D-Day)

---

## Database

SQLite with 5 tables:
- `schedules`: Schedule CRUD + recurrence
- `challenges`: Challenge tracking
- `earnings`: Revenue records per challenge
- `briefings`: Cached daily briefings
- `sqlite_sequence`: Auto-increment tracking

## Tech Stack

- **Backend**: FastAPI + Python 3.13
- **DB**: SQLite (aiosqlite)
- **STT**: faster-whisper (large-v3, CUDA)
- **TTS**: Edge TTS (ko-KR-SunHiNeural)
- **LLM**: Ollama qwen2.5:14b
- **Frontend**: React + TypeScript + Vite + Tailwind CSS
