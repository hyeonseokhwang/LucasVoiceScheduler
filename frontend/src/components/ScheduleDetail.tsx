import type { Schedule } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'

interface Props {
  schedule: Schedule
  onClose: () => void
  onEdit: () => void
  onRefresh: () => void
  addToast?: (
    type: 'success' | 'error' | 'info',
    message: string,
    options?: { action?: () => void; actionLabel?: string; duration?: number },
  ) => void
}

export function ScheduleDetail({ schedule, onClose, onEdit, onRefresh, addToast }: Props) {
  const cat = CATEGORIES[schedule.category] || CATEGORIES.general

  const formatDt = (s: string) => {
    const d = new Date(s)
    return d.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const handleComplete = async () => {
    try {
      await api.complete(schedule.id)
      addToast?.('success', '일정을 완료했습니다', {
        action: async () => {
          try {
            await api.update(schedule.id, { status: 'active' })
            onRefresh()
          } catch { /* ignore */ }
        },
        actionLabel: '되돌리기',
        duration: 5000,
      })
      onRefresh()
      onClose()
    } catch {
      addToast?.('error', '일정 완료 실패')
    }
  }

  const handleDelete = async () => {
    if (!confirm('이 일정을 삭제하시겠습니까?')) return
    try {
      await api.delete(schedule.id)
      addToast?.('success', '일정이 삭제되었습니다', {
        action: async () => {
          try {
            await api.update(schedule.id, { status: 'active' })
            onRefresh()
          } catch { /* ignore */ }
        },
        actionLabel: '되돌리기',
        duration: 5000,
      })
      onRefresh()
      onClose()
    } catch {
      addToast?.('error', '일정 삭제 실패')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    }
  }

  let recInfo: string | null = null
  if (schedule.recurrence) {
    try {
      const rec = JSON.parse(schedule.recurrence)
      const freqMap: Record<string, string> = { daily: '매일', weekly: '매주', monthly: '매월', yearly: '매년' }
      recInfo = freqMap[rec.freq] || rec.freq
      if (rec.interval > 1) recInfo = `${rec.interval}${(recInfo ?? '').replace('매', '')}마다`
      if (rec.until) recInfo = (recInfo ?? '') + ` (${rec.until}까지)`
    } catch { /* ignore */ }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4 animate-backdrop-in"
      onClick={onClose}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      <div
        className="bg-slate-800 rounded-xl border border-slate-700 p-6 max-w-lg w-full shadow-2xl animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cat.bg} ${cat.color} mb-2`}>
              {cat.label}
            </span>
            <h2 className="text-xl font-bold">{schedule.title}</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xl min-w-[44px] min-h-[44px] flex items-center justify-center">✕</button>
        </div>

        <div className="space-y-3 text-sm">
          <div className="flex gap-2">
            <span className="text-slate-400 w-16 shrink-0">시작</span>
            <span>{formatDt(schedule.start_at)}</span>
          </div>
          {schedule.end_at && (
            <div className="flex gap-2">
              <span className="text-slate-400 w-16 shrink-0">종료</span>
              <span>{formatDt(schedule.end_at)}</span>
            </div>
          )}
          {schedule.all_day ? (
            <div className="flex gap-2">
              <span className="text-slate-400 w-16 shrink-0">종일</span>
              <span>종일 일정</span>
            </div>
          ) : null}
          {recInfo && (
            <div className="flex gap-2">
              <span className="text-slate-400 w-16 shrink-0">반복</span>
              <span>{recInfo}</span>
            </div>
          )}
          {schedule.remind_at && (
            <div className="flex gap-2">
              <span className="text-slate-400 w-16 shrink-0">알림</span>
              <span>{formatDt(schedule.remind_at)}</span>
            </div>
          )}
          {schedule.description && (
            <div className="mt-4 p-3 bg-slate-900 rounded-lg text-slate-300">{schedule.description}</div>
          )}
          <div className="flex gap-2">
            <span className="text-slate-400 w-16 shrink-0">상태</span>
            <span className={schedule.status === 'completed' ? 'text-green-400' : 'text-blue-400'}>
              {schedule.status === 'active' ? '진행중' : schedule.status === 'completed' ? '완료' : '취소'}
            </span>
          </div>
        </div>

        <div className="flex gap-2 mt-6">
          <button
            onClick={onEdit}
            className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium transition-colors min-h-[44px]"
          >
            수정
          </button>
          {schedule.status === 'active' && (
            <button
              onClick={handleComplete}
              className="flex-1 py-2.5 bg-green-600 hover:bg-green-500 rounded-lg font-medium transition-colors min-h-[44px]"
            >
              완료
            </button>
          )}
          <button
            onClick={handleDelete}
            className="py-2.5 px-4 bg-red-600/20 hover:bg-red-600/40 text-red-400 rounded-lg font-medium transition-colors min-h-[44px]"
          >
            삭제
          </button>
        </div>
      </div>
    </div>
  )
}
