import type { Schedule, ScheduleFormData, Challenge, Earning, ChallengeProgress } from '../types'

const BASE = '/api/schedules'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  list(params?: { from_date?: string; to_date?: string; status?: string; category?: string }) {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([k, v]) => { if (v) qs.set(k, v) })
    }
    const q = qs.toString()
    return request<Schedule[]>(`${BASE}${q ? '?' + q : ''}`)
  },

  get(id: number) {
    return request<Schedule>(`${BASE}/${id}`)
  },

  create(data: ScheduleFormData) {
    return request<Schedule>(BASE, { method: 'POST', body: JSON.stringify(data) })
  },

  update(id: number, data: Partial<ScheduleFormData> & { status?: string }) {
    return request<Schedule>(`${BASE}/${id}`, { method: 'PUT', body: JSON.stringify(data) })
  },

  delete(id: number) {
    return request<{ ok: boolean }>(`${BASE}/${id}`, { method: 'DELETE' })
  },

  complete(id: number) {
    return request<Schedule>(`${BASE}/${id}/complete`, { method: 'POST' })
  },

  upcoming(hours = 24) {
    return request<Schedule[]>(`${BASE}/upcoming?hours=${hours}`)
  },

  calendar(year: number, month: number) {
    return request<Schedule[]>(`${BASE}/calendar/${year}/${month}`)
  },

  search(q: string) {
    return request<Schedule[]>(`${BASE}/search?q=${encodeURIComponent(q)}`)
  },

  voiceParse(text: string) {
    return request<{
      parsed: {
        title: string
        start_at: string
        end_at?: string
        all_day?: boolean
        category?: string
        description?: string
        recurrence?: object | null
      }
      confidence: number
      response: string
      conflicts: Schedule[]
    }>('/api/voice/parse', {
      method: 'POST',
      body: JSON.stringify({ text }),
    })
  },

  voiceConfirm(data: ScheduleFormData) {
    return request<Schedule>('/api/voice/confirm', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  voiceContext(date: string) {
    return request<{ schedules: Schedule[]; summary: string }>(`/api/voice/context?date=${date}`)
  },

  // Challenge API
  challengeList(status?: string) {
    const qs = status ? `?status=${status}` : ''
    return request<Challenge[]>(`/api/challenges${qs}`)
  },

  challengeGet(id: number) {
    return request<Challenge>(`/api/challenges/${id}`)
  },

  challengeCreate(data: { title: string; description?: string; target_amount: number; deadline: string; milestones?: object[] }) {
    return request<Challenge>('/api/challenges', { method: 'POST', body: JSON.stringify(data) })
  },

  challengeAddEarning(id: number, data: { amount: number; source?: string; date?: string; note?: string }) {
    return request<Earning>(`/api/challenges/${id}/earning`, { method: 'POST', body: JSON.stringify(data) })
  },

  challengeProgress(id: number) {
    return request<ChallengeProgress>(`/api/challenges/${id}/progress`)
  },

  challengeUpdateMilestone(challengeId: number, milestoneIndex: number, status: string) {
    return request<Challenge>(`/api/challenges/${challengeId}/milestone/${milestoneIndex}`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
  },

  async voiceTranscribe(audioBlob: Blob): Promise<{ text: string; duration: number; processing_time: number; error?: string }> {
    const formData = new FormData()
    formData.append('audio', audioBlob, 'recording.webm')
    const res = await fetch('/api/voice/transcribe', {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error('Transcription failed')
    return res.json()
  },
}
