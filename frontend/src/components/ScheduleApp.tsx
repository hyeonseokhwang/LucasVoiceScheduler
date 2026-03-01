import { useState, useEffect, useCallback, useRef } from 'react'
import type { Schedule, ViewMode } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'
import { useWebSocket } from '../hooks/useWebSocket'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
import { useDragDrop } from '../hooks/useDragDrop'
import { CalendarView } from './CalendarView'
import { ScheduleList } from './ScheduleList'
import { ScheduleForm } from './ScheduleForm'
import { ScheduleDetail } from './ScheduleDetail'
import { ReminderToast } from './ReminderToast'
import { Sidebar } from './Sidebar'
import { Toast, type ToastItem } from './Toast'
import { VoiceAssistant } from './VoiceAssistant'
import { QuickInput } from './QuickInput'
import { ChallengePage } from './ChallengePage'
import { StatsView } from './StatsView'

const MONTH_NAMES = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월']

export function ScheduleApp() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [selectedDate, setSelectedDate] = useState(now.toISOString().slice(0, 10))
  const [view, setView] = useState<ViewMode>('month')
  const [showList, setShowList] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [page, setPage] = useState<'calendar' | 'challenge' | 'stats'>('calendar')

  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(false)

  // Modal state
  const [showForm, setShowForm] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null)
  const [detailSchedule, setDetailSchedule] = useState<Schedule | null>(null)
  const [formInitialDate, setFormInitialDate] = useState<string | undefined>()

  // Category filter
  const [enabledCategories, setEnabledCategories] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {}
    for (const key of Object.keys(CATEGORIES)) initial[key] = true
    return initial
  })

  // Reminders
  const [reminders, setReminders] = useState<Schedule[]>([])

  // Toast
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const searchInputRef = useRef<HTMLInputElement | null>(null)

  const addToast = useCallback((
    type: 'success' | 'error' | 'info',
    message: string,
    options?: { action?: () => void; actionLabel?: string; duration?: number },
  ) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToasts((prev) => [...prev, { id, type, message, ...options }])
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const fetchSchedules = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.calendar(year, month)
      setSchedules(data)
    } catch (err) {
      console.error('Failed to fetch schedules:', err)
      addToast('error', '일정을 불러오지 못했습니다')
    } finally {
      setLoading(false)
    }
  }, [year, month, addToast])

  useEffect(() => {
    fetchSchedules()
  }, [fetchSchedules])

  // Filter schedules by enabled categories
  const filteredSchedules = schedules.filter((s) => enabledCategories[s.category] !== false)

  const handleReminder = useCallback((schedule: Schedule) => {
    setReminders((prev) => [...prev, schedule])
  }, [])

  useWebSocket(handleReminder)

  // Drag & drop
  const handleOptimisticUpdate = useCallback((schedule: Schedule, newStartAt: string, newEndAt: string | null) => {
    setSchedules((prev) =>
      prev.map((s) =>
        s.id === schedule.id ? { ...s, start_at: newStartAt, end_at: newEndAt } : s,
      ),
    )
  }, [])

  const { dragging, dragOverTarget, handleDragStart, handleDragOver, handleDragLeave, handleDrop, handleDragEnd } =
    useDragDrop({
      onMoved: fetchSchedules,
      onOptimisticUpdate: handleOptimisticUpdate,
      addToast,
    })

  // Navigation
  const goToday = useCallback(() => {
    const t = new Date()
    setYear(t.getFullYear())
    setMonth(t.getMonth() + 1)
    setSelectedDate(t.toISOString().slice(0, 10))
  }, [])

  const goPrev = useCallback(() => {
    if (month === 1) { setMonth(12); setYear((y) => y - 1) }
    else setMonth((m) => m - 1)
  }, [month])

  const goNext = useCallback(() => {
    if (month === 12) { setMonth(1); setYear((y) => y + 1) }
    else setMonth((m) => m + 1)
  }, [month])

  const handleSelectDate = useCallback((date: string) => {
    setSelectedDate(date)
    // If selecting a date in a different month, navigate there
    const [y, m] = date.split('-').map(Number)
    if (y !== year || m !== month) {
      setYear(y)
      setMonth(m)
    }
  }, [year, month])

  const handleSelectSchedule = useCallback((s: Schedule) => {
    setDetailSchedule(s)
  }, [])

  const handleEdit = useCallback(() => {
    if (detailSchedule) {
      setEditingSchedule(detailSchedule)
      setDetailSchedule(null)
      setFormInitialDate(undefined)
      setShowForm(true)
    }
  }, [detailSchedule])

  const handleCreate = useCallback(() => {
    setEditingSchedule(null)
    setFormInitialDate(selectedDate ? `${selectedDate}T09:00` : undefined)
    setShowForm(true)
  }, [selectedDate])

  const handleTimeSlotClick = useCallback((date: string, hour: number) => {
    setEditingSchedule(null)
    const h = String(hour).padStart(2, '0')
    setFormInitialDate(`${date}T${h}:00`)
    setShowForm(true)
  }, [])

  const handleToggleCategory = useCallback((cat: string) => {
    setEnabledCategories((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }, [])

  const isModalOpen = showForm || !!detailSchedule

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onNewSchedule: handleCreate,
    onToday: goToday,
    onPrev: goPrev,
    onNext: goNext,
    onSetView: (v) => { setView(v); setShowList(false) },
    onFocusSearch: () => searchInputRef.current?.focus(),
    isModalOpen,
  })

  const views: { mode: ViewMode; label: string }[] = [
    { mode: 'month', label: '월' },
    { mode: 'week', label: '주' },
    { mode: 'day', label: '일' },
  ]

  return (
    <div className="min-h-screen bg-slate-900">
      <ReminderToast reminders={reminders} />
      <Toast toasts={toasts} onRemove={removeToast} />

      {/* Header */}
      <header className="sticky top-0 z-20 bg-slate-900/95 backdrop-blur border-b border-slate-700/50">
        <div className="max-w-full mx-auto px-4 py-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            {/* Left: sidebar toggle + title + nav */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="p-2 hover:bg-slate-700 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center text-slate-400 hover:text-white lg:hidden"
                title="사이드바 토글"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <h1 className="text-lg font-bold text-blue-400 hidden sm:block">Lucas Scheduler</h1>
              <div className="flex items-center gap-1">
                <button onClick={goPrev} className="p-2 hover:bg-slate-700 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center">
                  ◀
                </button>
                <span className="text-lg font-semibold min-w-[120px] text-center">
                  {year}년 {MONTH_NAMES[month - 1]}
                </span>
                <button onClick={goNext} className="p-2 hover:bg-slate-700 rounded-lg min-w-[44px] min-h-[44px] flex items-center justify-center">
                  ▶
                </button>
              </div>
              <button onClick={goToday} className="px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg min-h-[44px]">
                오늘
              </button>
            </div>

            {/* Center: Quick natural language input */}
            <div className="hidden md:block flex-1 max-w-md mx-4">
              <QuickInput onScheduleCreated={fetchSchedules} addToast={addToast} />
            </div>

            {/* Right: page switcher + view switcher + actions */}
            <div className="flex items-center gap-2">
              {/* Page tabs */}
              <div className="flex bg-slate-800 rounded-lg p-0.5">
                <button
                  onClick={() => setPage('calendar')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors min-h-[36px] ${
                    page === 'calendar' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  일정
                </button>
                <button
                  onClick={() => setPage('challenge')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors min-h-[36px] ${
                    page === 'challenge' ? 'bg-amber-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  챌린지
                </button>
                <button
                  onClick={() => setPage('stats')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors min-h-[36px] ${
                    page === 'stats' ? 'bg-purple-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  통계
                </button>
              </div>

              {/* Calendar view switcher (only on calendar page) */}
              {page === 'calendar' && (
                <div className="flex bg-slate-800 rounded-lg p-0.5">
                  {views.map(({ mode, label }) => (
                    <button
                      key={mode}
                      onClick={() => { setView(mode); setShowList(false) }}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors min-h-[36px] ${
                        view === mode && !showList ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                  <button
                    onClick={() => setShowList(!showList)}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors min-h-[36px] ${
                      showList ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    목록
                  </button>
                </div>
              )}

              {page === 'calendar' && (
                <button
                  onClick={handleCreate}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium text-sm transition-colors min-h-[44px]"
                >
                  + 새 일정
                </button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main layout: Sidebar + Content */}
      <div className="flex max-w-full mx-auto">
        {/* Sidebar - hidden on mobile by default, toggleable */}
        <div className={`${sidebarOpen ? 'block' : 'hidden'} lg:block shrink-0 border-r border-slate-700/50 p-4`}>
          <Sidebar
            year={year}
            month={month}
            selectedDate={selectedDate}
            schedules={schedules}
            enabledCategories={enabledCategories}
            onToggleCategory={handleToggleCategory}
            onSelectDate={handleSelectDate}
            onSelectSchedule={handleSelectSchedule}
            searchInputRef={searchInputRef}
            addToast={addToast}
          />
        </div>

        {/* Main content */}
        <main className="flex-1 min-w-0 px-4 py-4">
          {page === 'challenge' && (
            <ChallengePage addToast={addToast} />
          )}

          {page === 'stats' && (
            <StatsView />
          )}

          {page === 'calendar' && (
            <>
              {loading && (
                <div className="flex items-center justify-center py-12">
                  <svg className="animate-spin h-8 w-8 text-blue-500" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                </div>
              )}

              {!loading && showList ? (
                <ScheduleList schedules={filteredSchedules} onSelect={handleSelectSchedule} />
              ) : !loading ? (
                <CalendarView
                  year={year}
                  month={month}
                  selectedDate={selectedDate}
                  schedules={filteredSchedules}
                  view={view}
                  onSelectDate={handleSelectDate}
                  onSelectSchedule={handleSelectSchedule}
                  onTimeSlotClick={handleTimeSlotClick}
                  dragging={dragging}
                  dragOverTarget={dragOverTarget}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onDragEnd={handleDragEnd}
                />
              ) : null}

              {/* Empty state */}
              {!loading && filteredSchedules.length === 0 && !showList && (
                <div className="text-center py-16">
                  <div className="text-5xl mb-4 opacity-30">📅</div>
                  <p className="text-slate-500 text-lg mb-2">이번 달 일정이 없습니다</p>
                  <p className="text-slate-600 text-sm mb-4">새 일정을 만들어보세요</p>
                  <button
                    onClick={handleCreate}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
                  >
                    + 새 일정 만들기
                  </button>
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {/* Modals */}
      {showForm && (
        <ScheduleForm
          schedule={editingSchedule}
          initialDate={formInitialDate}
          onClose={() => { setShowForm(false); setEditingSchedule(null) }}
          onSaved={fetchSchedules}
          addToast={addToast}
        />
      )}

      {detailSchedule && (
        <ScheduleDetail
          schedule={detailSchedule}
          onClose={() => setDetailSchedule(null)}
          onEdit={handleEdit}
          onRefresh={fetchSchedules}
          addToast={addToast}
        />
      )}

      {/* Voice Assistant FAB */}
      <VoiceAssistant onScheduleCreated={fetchSchedules} addToast={addToast} />
    </div>
  )
}
