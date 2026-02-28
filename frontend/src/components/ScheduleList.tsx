import type { Schedule } from '../types'
import { CATEGORIES } from '../types'

interface Props {
  schedules: Schedule[]
  onSelect: (s: Schedule) => void
}

export function ScheduleList({ schedules, onSelect }: Props) {
  const formatTime = (s: string) => {
    const d = new Date(s)
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }

  const formatDate = (s: string) => {
    const d = new Date(s)
    return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', weekday: 'short' })
  }

  if (schedules.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <div className="text-4xl mb-3">📅</div>
        <p>일정이 없습니다</p>
      </div>
    )
  }

  // Group by date
  const grouped: Record<string, Schedule[]> = {}
  for (const s of schedules) {
    const date = s.start_at.slice(0, 10)
    if (!grouped[date]) grouped[date] = []
    grouped[date].push(s)
  }

  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([date, items]) => (
        <div key={date}>
          <h3 className="text-sm font-medium text-slate-400 mb-2 sticky top-0 bg-slate-900 py-1">
            {formatDate(items[0].start_at)}
          </h3>
          <div className="space-y-1">
            {items.map((s, idx) => {
              const cat = CATEGORIES[s.category] || CATEGORIES.general
              return (
                <button
                  key={s._is_occurrence ? `${s.id}-${s._occurrence_date}` : (s.id ?? idx)}
                  onClick={() => onSelect(s)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors min-h-[44px] ${cat.bg} hover:brightness-125`}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col items-center min-w-[48px]">
                      {s.all_day ? (
                        <span className="text-xs text-slate-400">종일</span>
                      ) : (
                        <span className="text-xs text-slate-400">{formatTime(s.start_at)}</span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className={`font-medium truncate ${s.status === 'completed' ? 'line-through text-slate-500' : ''}`}>
                        {s.title}
                      </div>
                      {s.description && (
                        <div className="text-xs text-slate-400 truncate mt-0.5">{s.description}</div>
                      )}
                    </div>
                    {s.recurrence && <span className="text-xs text-slate-500">🔁</span>}
                    {s.status === 'completed' && <span className="text-xs text-green-500">✓</span>}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
