import { useMemo } from 'react'
import type { Schedule, ViewMode } from '../types'
import { CATEGORIES } from '../types'

interface Props {
  year: number
  month: number
  selectedDate: string
  schedules: Schedule[]
  view: ViewMode
  onSelectDate: (date: string) => void
  onSelectSchedule: (s: Schedule) => void
  onTimeSlotClick?: (date: string, hour: number) => void
  // Drag & drop
  dragging?: Schedule | null
  dragOverTarget?: string | null
  onDragStart?: (e: React.DragEvent, s: Schedule) => void
  onDragOver?: (e: React.DragEvent, targetId: string) => void
  onDragLeave?: () => void
  onDrop?: (e: React.DragEvent, date: string, hour?: number) => void
  onDragEnd?: () => void
}

const DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']

function getMonthGrid(year: number, month: number) {
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
    days.push({ date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`, day: d, inMonth: false })
  }

  for (let d = 1; d <= lastDay; d++) {
    days.push({ date: `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`, day: d, inMonth: true })
  }

  const remaining = 7 - (days.length % 7)
  if (remaining < 7) {
    for (let d = 1; d <= remaining; d++) {
      const m = month + 1 > 12 ? 1 : month + 1
      const y = month + 1 > 12 ? year + 1 : year
      days.push({ date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`, day: d, inMonth: false })
    }
  }

  return days
}

function getWeekDays(dateStr: string) {
  const d = new Date(dateStr)
  const dow = d.getDay()
  const monday = new Date(d)
  monday.setDate(d.getDate() - ((dow + 6) % 7))

  const days: string[] = []
  for (let i = 0; i < 7; i++) {
    const day = new Date(monday)
    day.setDate(monday.getDate() + i)
    days.push(day.toISOString().slice(0, 10))
  }
  return days
}

/** Layout overlapping events into columns */
function layoutEvents(events: Schedule[]): { schedule: Schedule; column: number; totalColumns: number }[] {
  if (events.length === 0) return []

  const sorted = [...events].sort((a, b) => a.start_at.localeCompare(b.start_at))
  const getEnd = (s: Schedule) => s.end_at || new Date(new Date(s.start_at).getTime() + 3600000).toISOString()

  // Build overlap groups
  const groups: Schedule[][] = []
  let currentGroup: Schedule[] = [sorted[0]]
  let groupEnd = getEnd(sorted[0])

  for (let i = 1; i < sorted.length; i++) {
    const s = sorted[i]
    if (s.start_at < groupEnd) {
      currentGroup.push(s)
      const sEnd = getEnd(s)
      if (sEnd > groupEnd) groupEnd = sEnd
    } else {
      groups.push(currentGroup)
      currentGroup = [s]
      groupEnd = getEnd(s)
    }
  }
  groups.push(currentGroup)

  const result: { schedule: Schedule; column: number; totalColumns: number }[] = []

  for (const group of groups) {
    // Assign columns within group
    const columns: Schedule[][] = []
    for (const s of group) {
      let placed = false
      for (let c = 0; c < columns.length; c++) {
        const lastInCol = columns[c][columns[c].length - 1]
        if (getEnd(lastInCol) <= s.start_at) {
          columns[c].push(s)
          placed = true
          break
        }
      }
      if (!placed) {
        columns.push([s])
      }
    }
    const totalColumns = columns.length
    for (let c = 0; c < columns.length; c++) {
      for (const s of columns[c]) {
        result.push({ schedule: s, column: c, totalColumns })
      }
    }
  }

  return result
}

const HOURS = Array.from({ length: 24 }, (_, i) => i)

export function CalendarView({
  year,
  month,
  selectedDate,
  schedules,
  view,
  onSelectDate,
  onSelectSchedule,
  onTimeSlotClick,
  dragging,
  dragOverTarget,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
}: Props) {
  const today = new Date().toISOString().slice(0, 10)

  const schedulesByDate = useMemo(() => {
    const map: Record<string, Schedule[]> = {}
    for (const s of schedules) {
      const date = s.start_at.slice(0, 10)
      if (!map[date]) map[date] = []
      map[date].push(s)
    }
    return map
  }, [schedules])

  // ── MONTH VIEW ──
  if (view === 'month') {
    const grid = getMonthGrid(year, month)
    return (
      <div>
        <div className="grid grid-cols-7 gap-px mb-px">
          {DAY_NAMES.map((name) => (
            <div key={name} className="text-center text-xs font-medium text-slate-500 py-2">{name}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-px bg-slate-700/30">
          {grid.map(({ date, day, inMonth }) => {
            const isToday = date === today
            const isSelected = date === selectedDate
            const daySchedules = schedulesByDate[date] || []
            const isDragOver = dragOverTarget === `month-${date}`
            return (
              <div
                key={date}
                onClick={() => onSelectDate(date)}
                onDragOver={(e) => onDragOver?.(e, `month-${date}`)}
                onDragLeave={() => onDragLeave?.()}
                onDrop={(e) => onDrop?.(e, date)}
                className={`min-h-[80px] sm:min-h-[100px] p-1 text-left transition-colors cursor-pointer ${
                  inMonth ? 'bg-slate-800/80' : 'bg-slate-900/50'
                } ${isSelected ? 'ring-2 ring-blue-500' : ''} ${
                  isDragOver ? 'ring-2 ring-blue-500/50 bg-blue-500/10' : ''
                } hover:bg-slate-700/60`}
              >
                <div className={`text-xs font-medium mb-1 w-6 h-6 flex items-center justify-center rounded-full ${
                  isToday ? 'bg-blue-600 text-white' : inMonth ? 'text-slate-300' : 'text-slate-600'
                }`}>
                  {day}
                </div>
                <div className="space-y-0.5">
                  {daySchedules.slice(0, 3).map((s, i) => {
                    const cat = CATEGORIES[s.category] || CATEGORIES.general
                    const isDraggingThis = dragging?.id === s.id
                    return (
                      <div
                        key={`${s.id}-${i}`}
                        draggable={!s._is_occurrence}
                        onDragStart={(e) => onDragStart?.(e, s)}
                        onDragEnd={() => onDragEnd?.()}
                        onClick={(e) => { e.stopPropagation(); onSelectSchedule(s) }}
                        className={`text-[10px] sm:text-xs truncate px-1 py-0.5 rounded ${cat.bg} ${cat.color} cursor-pointer hover:brightness-125 ${
                          isDraggingThis ? 'opacity-50' : ''
                        }`}
                      >
                        {s.title}
                      </div>
                    )
                  })}
                  {daySchedules.length > 3 && (
                    <div className="text-[10px] text-slate-500 px-1">+{daySchedules.length - 3}개</div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // ── WEEK VIEW ──
  if (view === 'week') {
    const weekDays = getWeekDays(selectedDate)
    return (
      <div className="overflow-x-auto">
        {/* Header */}
        <div className="grid grid-cols-[60px_repeat(7,1fr)] gap-px sticky top-0 bg-slate-900 z-10">
          <div />
          {weekDays.map((date, i) => {
            const d = new Date(date)
            const isToday = date === today
            return (
              <button
                key={date}
                onClick={() => onSelectDate(date)}
                className={`text-center py-2 ${date === selectedDate ? 'bg-slate-700' : ''}`}
              >
                <div className="text-xs text-slate-500">{DAY_NAMES[i]}</div>
                <div className={`text-sm font-medium w-7 h-7 mx-auto flex items-center justify-center rounded-full ${
                  isToday ? 'bg-blue-600 text-white' : 'text-slate-300'
                }`}>
                  {d.getDate()}
                </div>
              </button>
            )
          })}
        </div>
        {/* Time grid */}
        <div className="grid grid-cols-[60px_repeat(7,1fr)] gap-px">
          {HOURS.map((hour) => (
            <div key={hour} className="contents">
              <div className="text-xs text-slate-500 text-right pr-2 py-3 h-14">
                {String(hour).padStart(2, '0')}:00
              </div>
              {weekDays.map((date) => {
                const daySchedules = (schedulesByDate[date] || []).filter((s) => {
                  if (s.all_day) return false
                  const h = new Date(s.start_at).getHours()
                  return h === hour
                })
                const laid = layoutEvents(daySchedules)
                const targetId = `week-${date}-${hour}`
                const isDragOver = dragOverTarget === targetId

                return (
                  <div
                    key={targetId}
                    onClick={(e) => {
                      if ((e.target as HTMLElement).closest('[data-schedule]')) return
                      onTimeSlotClick?.(date, hour)
                    }}
                    onDragOver={(e) => onDragOver?.(e, targetId)}
                    onDragLeave={() => onDragLeave?.()}
                    onDrop={(e) => onDrop?.(e, date, hour)}
                    className={`border-t border-slate-700/50 h-14 relative hover:bg-slate-800/60 transition-colors cursor-pointer ${
                      isDragOver ? 'ring-2 ring-blue-500/50 bg-blue-500/10' : ''
                    }`}
                  >
                    {laid.map(({ schedule: s, column, totalColumns }) => {
                      const cat = CATEGORIES[s.category] || CATEGORIES.general
                      const isDraggingThis = dragging?.id === s.id
                      const width = `${(1 / totalColumns) * 100}%`
                      const left = `${(column / totalColumns) * 100}%`

                      return (
                        <div
                          key={`${s.id}-${column}`}
                          data-schedule
                          draggable={!s._is_occurrence}
                          onDragStart={(e) => { e.stopPropagation(); onDragStart?.(e, s) }}
                          onDragEnd={() => onDragEnd?.()}
                          onClick={(e) => { e.stopPropagation(); onSelectSchedule(s) }}
                          className={`absolute top-0 bottom-0 mx-0.5 text-[10px] sm:text-xs truncate px-1 py-0.5 rounded ${cat.bg} ${cat.color} cursor-pointer hover:brightness-125 ${
                            isDraggingThis ? 'opacity-50' : ''
                          }`}
                          style={{ width, left }}
                        >
                          {s.title}
                        </div>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ── DAY VIEW ──
  const dayAllDay = (schedulesByDate[selectedDate] || []).filter((s) => s.all_day)
  const dayTimed = (schedulesByDate[selectedDate] || []).filter((s) => !s.all_day)

  return (
    <div>
      {/* All-day events */}
      {dayAllDay.length > 0 && (
        <div className="border-b border-slate-700 pb-2 mb-2">
          <div className="text-xs text-slate-500 mb-1 px-2">종일</div>
          {dayAllDay.map((s, i) => {
            const cat = CATEGORIES[s.category] || CATEGORIES.general
            return (
              <div
                key={`allday-${s.id}-${i}`}
                onClick={() => onSelectSchedule(s)}
                className={`mx-2 text-sm px-2 py-1 rounded ${cat.bg} ${cat.color} cursor-pointer mb-1 hover:brightness-125`}
              >
                {s.title}
              </div>
            )
          })}
        </div>
      )}

      {/* Hourly grid */}
      <div className="grid grid-cols-[60px_1fr] gap-px">
        {HOURS.map((hour) => {
          const hourSchedules = dayTimed.filter((s) => new Date(s.start_at).getHours() === hour)
          const laid = layoutEvents(hourSchedules)
          const targetId = `day-${selectedDate}-${hour}`
          const isDragOver = dragOverTarget === targetId

          return (
            <div key={hour} className="contents">
              <div className="text-xs text-slate-500 text-right pr-3 py-3 h-16">
                {String(hour).padStart(2, '0')}:00
              </div>
              <div
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest('[data-schedule]')) return
                  onTimeSlotClick?.(selectedDate, hour)
                }}
                onDragOver={(e) => onDragOver?.(e, targetId)}
                onDragLeave={() => onDragLeave?.()}
                onDrop={(e) => onDrop?.(e, selectedDate, hour)}
                className={`border-t border-slate-700/50 h-16 relative hover:bg-slate-800/60 transition-colors cursor-pointer ${
                  isDragOver ? 'ring-2 ring-blue-500/50 bg-blue-500/10' : ''
                }`}
              >
                {laid.map(({ schedule: s, column, totalColumns }) => {
                  const cat = CATEGORIES[s.category] || CATEGORIES.general
                  const isDraggingThis = dragging?.id === s.id
                  const width = `calc(${(1 / totalColumns) * 100}% - 4px)`
                  const left = `calc(${(column / totalColumns) * 100}% + 2px)`

                  return (
                    <div
                      key={`${s.id}-${column}`}
                      data-schedule
                      draggable={!s._is_occurrence}
                      onDragStart={(e) => { e.stopPropagation(); onDragStart?.(e, s) }}
                      onDragEnd={() => onDragEnd?.()}
                      onClick={(e) => { e.stopPropagation(); onSelectSchedule(s) }}
                      className={`absolute top-0 bottom-1 text-sm px-2 py-1 rounded ${cat.bg} ${cat.color} cursor-pointer hover:brightness-125 ${
                        isDraggingThis ? 'opacity-50' : ''
                      }`}
                      style={{ width, left }}
                    >
                      <span className="font-medium">{s.title}</span>
                      <span className="ml-2 text-xs opacity-70">
                        {new Date(s.start_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
