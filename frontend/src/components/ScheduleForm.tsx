import { useState, useEffect } from 'react'
import type { Schedule, ScheduleFormData, Recurrence } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'

interface Props {
  schedule?: Schedule | null
  initialDate?: string
  onClose: () => void
  onSaved: () => void
  addToast?: (type: 'success' | 'error' | 'info', message: string) => void
}

export function ScheduleForm({ schedule, initialDate, onClose, onSaved, addToast }: Props) {
  const isEdit = !!schedule

  const toLocalDt = (iso?: string | null) => {
    if (!iso) return ''
    return iso.length >= 16 ? iso.slice(0, 16) : iso
  }

  const [form, setForm] = useState<ScheduleFormData>({
    title: schedule?.title || '',
    description: schedule?.description || '',
    start_at: toLocalDt(schedule?.start_at) || initialDate || '',
    end_at: toLocalDt(schedule?.end_at) || '',
    all_day: !!(schedule?.all_day),
    category: schedule?.category || 'general',
    remind_at: toLocalDt(schedule?.remind_at) || '',
    recurrence: null,
  })

  const [showRecurrence, setShowRecurrence] = useState(false)
  const [rec, setRec] = useState<Recurrence>({
    freq: 'weekly',
    interval: 1,
    days: [],
    until: '',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (schedule?.recurrence) {
      try {
        const parsed = JSON.parse(schedule.recurrence)
        setRec(parsed)
        setShowRecurrence(true)
      } catch { /* ignore */ }
    }
  }, [schedule])

  // Auto-set end_at 1 hour after start_at if not set
  useEffect(() => {
    if (form.start_at && !form.end_at && !form.all_day && !isEdit) {
      const start = new Date(form.start_at)
      if (!isNaN(start.getTime())) {
        const end = new Date(start.getTime() + 60 * 60 * 1000)
        const y = end.getFullYear()
        const m = String(end.getMonth() + 1).padStart(2, '0')
        const d = String(end.getDate()).padStart(2, '0')
        const h = String(end.getHours()).padStart(2, '0')
        const min = String(end.getMinutes()).padStart(2, '0')
        setForm((prev) => ({ ...prev, end_at: `${y}-${m}-${d}T${h}:${min}` }))
      }
    }
  }, [form.start_at, form.all_day, isEdit])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const data: ScheduleFormData = {
        ...form,
        recurrence: showRecurrence ? rec : null,
      }
      if (isEdit && schedule) {
        await api.update(schedule.id, data)
        addToast?.('success', '일정이 수정되었습니다')
      } else {
        await api.create(data)
        addToast?.('success', '일정이 생성되었습니다')
      }
      onSaved()
      onClose()
    } catch (err) {
      addToast?.('error', `일정 저장 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`)
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    }
  }

  const dayNames = ['월', '화', '수', '목', '금', '토', '일']

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4 animate-backdrop-in"
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div
        className="bg-slate-800 rounded-xl border border-slate-700 p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">{isEdit ? '일정 수정' : '새 일정'}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xl min-w-[44px] min-h-[44px] flex items-center justify-center">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">제목 *</label>
            <input
              type="text"
              required
              autoFocus
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2.5 focus:border-blue-500 focus:outline-none min-h-[44px]"
              placeholder="일정 제목"
            />
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">카테고리</label>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(CATEGORIES).map(([key, val]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setForm({ ...form, category: key })}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors min-h-[44px] ${
                    form.category === key
                      ? `${val.bg} ${val.color} border-current`
                      : 'bg-slate-900 border-slate-600 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  {val.label}
                </button>
              ))}
            </div>
          </div>

          {/* All day toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.all_day}
              onChange={(e) => setForm({ ...form, all_day: e.target.checked })}
              className="w-5 h-5 rounded bg-slate-900 border-slate-600"
            />
            <span className="text-sm">종일 일정</span>
          </label>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-slate-400 mb-1">시작 *</label>
              <input
                type={form.all_day ? 'date' : 'datetime-local'}
                required
                value={form.all_day ? form.start_at.slice(0, 10) : form.start_at}
                onChange={(e) => setForm({ ...form, start_at: e.target.value })}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2.5 focus:border-blue-500 focus:outline-none min-h-[44px]"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">종료</label>
              <input
                type={form.all_day ? 'date' : 'datetime-local'}
                value={form.all_day ? (form.end_at?.slice(0, 10) || '') : (form.end_at || '')}
                onChange={(e) => setForm({ ...form, end_at: e.target.value })}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2.5 focus:border-blue-500 focus:outline-none min-h-[44px]"
              />
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">설명</label>
            <textarea
              value={form.description || ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={3}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2.5 focus:border-blue-500 focus:outline-none resize-none"
              placeholder="메모"
            />
          </div>

          {/* Reminder */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">알림</label>
            <input
              type="datetime-local"
              value={form.remind_at || ''}
              onChange={(e) => setForm({ ...form, remind_at: e.target.value })}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2.5 focus:border-blue-500 focus:outline-none min-h-[44px]"
            />
          </div>

          {/* Recurrence */}
          <div>
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={showRecurrence}
                onChange={(e) => setShowRecurrence(e.target.checked)}
                className="w-5 h-5 rounded bg-slate-900 border-slate-600"
              />
              <span className="text-sm">반복 일정</span>
            </label>
            {showRecurrence && (
              <div className="bg-slate-900 rounded-lg p-3 space-y-3 animate-fade-in">
                <div className="flex gap-3">
                  <select
                    value={rec.freq}
                    onChange={(e) => setRec({ ...rec, freq: e.target.value as Recurrence['freq'] })}
                    className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 min-h-[44px]"
                  >
                    <option value="daily">매일</option>
                    <option value="weekly">매주</option>
                    <option value="monthly">매월</option>
                    <option value="yearly">매년</option>
                  </select>
                  <input
                    type="number"
                    min={1}
                    max={99}
                    value={rec.interval}
                    onChange={(e) => setRec({ ...rec, interval: parseInt(e.target.value) || 1 })}
                    className="w-20 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 min-h-[44px]"
                  />
                  <span className="self-center text-sm text-slate-400">간격</span>
                </div>
                {rec.freq === 'weekly' && (
                  <div className="flex gap-1">
                    {dayNames.map((name, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => {
                          const days = rec.days || []
                          setRec({
                            ...rec,
                            days: days.includes(i) ? days.filter((d) => d !== i) : [...days, i],
                          })
                        }}
                        className={`w-10 h-10 rounded-lg text-sm font-medium transition-colors ${
                          rec.days?.includes(i)
                            ? 'bg-blue-600 text-white'
                            : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                        }`}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                )}
                <div>
                  <label className="text-xs text-slate-400">종료일</label>
                  <input
                    type="date"
                    value={rec.until || ''}
                    onChange={(e) => setRec({ ...rec, until: e.target.value })}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 mt-1 min-h-[44px]"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Submit */}
          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:cursor-not-allowed rounded-lg font-medium transition-colors min-h-[44px] flex items-center justify-center gap-2"
            >
              {submitting && (
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {isEdit ? '수정' : '생성'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-2.5 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors min-h-[44px]"
            >
              취소
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
