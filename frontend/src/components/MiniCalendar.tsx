import { useMemo } from 'react'
import type { Schedule } from '../types'

interface Props {
  year: number
  month: number
  selectedDate: string
  schedules: Schedule[]
  onSelectDate: (date: string) => void
}

const DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']

export function MiniCalendar({ year, month, selectedDate, schedules, onSelectDate }: Props) {
  const today = new Date().toISOString().slice(0, 10)

  const datesWithEvents = useMemo(() => {
    const set = new Set<string>()
    for (const s of schedules) {
      set.add(s.start_at.slice(0, 10))
    }
    return set
  }, [schedules])

  const grid = useMemo(() => {
    const first = new Date(year, month - 1, 1)
    const lastDay = new Date(year, month, 0).getDate()
    let startDow = first.getDay() - 1
    if (startDow < 0) startDow = 6

    const days: { date: string; day: number; inMonth: boolean }[] = []

    const prevLast = new Date(year, month - 1, 0).getDate()
    for (let i = startDow - 1; i >= 0; i--) {
      const d = prevLast - i
      const m = month - 1 <= 0 ? 12 : month - 1
      const y = month - 1 <= 0 ? year - 1 : year
      days.push({
        date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
        day: d,
        inMonth: false,
      })
    }

    for (let d = 1; d <= lastDay; d++) {
      days.push({
        date: `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
        day: d,
        inMonth: true,
      })
    }

    const remaining = 7 - (days.length % 7)
    if (remaining < 7) {
      for (let d = 1; d <= remaining; d++) {
        const m = month + 1 > 12 ? 1 : month + 1
        const y = month + 1 > 12 ? year + 1 : year
        days.push({
          date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
          day: d,
          inMonth: false,
        })
      }
    }

    return days
  }, [year, month])

  return (
    <div>
      <div className="grid grid-cols-7 gap-0">
        {DAY_NAMES.map((name) => (
          <div key={name} className="text-center text-[10px] font-medium text-slate-500 py-1">
            {name}
          </div>
        ))}
        {grid.map(({ date, day, inMonth }) => {
          const isToday = date === today
          const isSelected = date === selectedDate
          const hasEvents = datesWithEvents.has(date)

          return (
            <button
              key={date}
              onClick={() => onSelectDate(date)}
              className={`relative w-7 h-7 mx-auto text-[11px] rounded-full flex items-center justify-center transition-colors ${
                isSelected
                  ? 'bg-blue-600 text-white'
                  : isToday
                    ? 'bg-blue-600/30 text-blue-400'
                    : inMonth
                      ? 'text-slate-300 hover:bg-slate-700'
                      : 'text-slate-600'
              }`}
            >
              {day}
              {hasEvents && !isSelected && (
                <span className="absolute bottom-0.5 w-1 h-1 rounded-full bg-blue-400" />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
