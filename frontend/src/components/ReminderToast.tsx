import { useEffect, useState, useCallback } from 'react'
import type { Schedule } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'

interface ReminderEntry {
  id: number
  schedule: Schedule
  timestamp: Date
  snoozed?: boolean
}

let toastId = 0

interface Props {
  reminders: Schedule[]
}

export function ReminderToast({ reminders }: Props) {
  const [toasts, setToasts] = useState<ReminderEntry[]>([])
  const [history, setHistory] = useState<ReminderEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    if (reminders.length === 0) return
    const latest = reminders[reminders.length - 1]
    const id = ++toastId
    const entry: ReminderEntry = { id, schedule: latest, timestamp: new Date() }
    setToasts((prev) => [...prev, entry])
    setHistory((prev) => [entry, ...prev].slice(0, 50)) // Keep last 50

    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 10000)
    return () => clearTimeout(timer)
  }, [reminders])

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const snooze = useCallback(async (entry: ReminderEntry, minutes: number) => {
    dismiss(entry.id)
    try {
      // Set a new remind_at in the future
      const newRemindAt = new Date(Date.now() + minutes * 60 * 1000)
      const y = newRemindAt.getFullYear()
      const m = String(newRemindAt.getMonth() + 1).padStart(2, '0')
      const d = String(newRemindAt.getDate()).padStart(2, '0')
      const h = String(newRemindAt.getHours()).padStart(2, '0')
      const min = String(newRemindAt.getMinutes()).padStart(2, '0')
      const remindStr = `${y}-${m}-${d}T${h}:${min}`

      if (!entry.schedule._is_occurrence) {
        await api.update(entry.schedule.id, { remind_at: remindStr })
      }

      // Update history
      setHistory((prev) =>
        prev.map((h) => (h.id === entry.id ? { ...h, snoozed: true } : h)),
      )
    } catch (err) {
      console.error('Snooze failed:', err)
    }
  }, [dismiss])

  return (
    <>
      {/* Active reminder toasts */}
      {toasts.length > 0 && (
        <div className="fixed top-16 right-4 z-50 flex flex-col gap-2 max-w-sm">
          {toasts.map((entry) => {
            const cat = CATEGORIES[entry.schedule.category] || CATEGORIES.general
            return (
              <div
                key={entry.id}
                className={`relative border rounded-xl p-4 shadow-xl animate-toast-in backdrop-blur-sm ${cat.bg}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">🔔</span>
                  <span className={`font-semibold ${cat.color}`}>{entry.schedule.title}</span>
                </div>
                {entry.schedule.description && (
                  <p className="text-sm text-slate-300 ml-7 mb-2">{entry.schedule.description}</p>
                )}
                <div className="text-xs text-slate-400 ml-7 mb-2">
                  {new Date(entry.schedule.start_at).toLocaleString('ko-KR', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>

                {/* Snooze buttons */}
                <div className="flex gap-1.5 ml-7">
                  <button
                    onClick={() => snooze(entry, 5)}
                    className="px-2 py-1 bg-slate-700/80 hover:bg-slate-600 rounded text-xs transition-colors"
                  >
                    5분 후
                  </button>
                  <button
                    onClick={() => snooze(entry, 15)}
                    className="px-2 py-1 bg-slate-700/80 hover:bg-slate-600 rounded text-xs transition-colors"
                  >
                    15분 후
                  </button>
                  <button
                    onClick={() => snooze(entry, 60)}
                    className="px-2 py-1 bg-slate-700/80 hover:bg-slate-600 rounded text-xs transition-colors"
                  >
                    1시간 후
                  </button>
                </div>

                <button
                  onClick={() => dismiss(entry.id)}
                  className="absolute top-2 right-2 text-slate-400 hover:text-slate-200 w-6 h-6 flex items-center justify-center"
                >
                  ✕
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* History toggle button */}
      {history.length > 0 && toasts.length === 0 && (
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="fixed top-16 right-4 z-40 p-2 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
          title="알림 이력"
        >
          <span className="text-sm">🔔</span>
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-600 rounded-full text-[10px] flex items-center justify-center">
            {history.length}
          </span>
        </button>
      )}

      {/* History panel */}
      {showHistory && (
        <div className="fixed top-28 right-4 z-40 w-80 max-h-96 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden animate-fade-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
            <h3 className="text-sm font-semibold">알림 이력</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setHistory([])}
                className="text-xs text-slate-500 hover:text-slate-300"
              >
                모두 지우기
              </button>
              <button
                onClick={() => setShowHistory(false)}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="overflow-y-auto max-h-80">
            {history.length === 0 ? (
              <div className="p-4 text-center text-sm text-slate-500">알림 이력이 없습니다</div>
            ) : (
              history.map((entry) => {
                const cat = CATEGORIES[entry.schedule.category] || CATEGORIES.general
                return (
                  <div
                    key={entry.id}
                    className="px-4 py-2.5 border-b border-slate-700/30 last:border-b-0"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${cat.bg.split(' ')[0]}`} />
                      <span className="text-sm font-medium truncate">{entry.schedule.title}</span>
                      {entry.snoozed && (
                        <span className="text-[10px] text-yellow-400 bg-yellow-400/10 px-1 rounded">스누즈</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 ml-4 mt-0.5">
                      {entry.timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </>
  )
}
