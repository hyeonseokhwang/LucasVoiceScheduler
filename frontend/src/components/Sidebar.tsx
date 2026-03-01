import { useState, useEffect, useRef } from 'react'
import type { Schedule } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'
import { MiniCalendar } from './MiniCalendar'
import { SearchResults } from './SearchResults'
import { ChallengeCard } from './ChallengeCard'

interface Props {
  year: number
  month: number
  selectedDate: string
  schedules: Schedule[]
  enabledCategories: Record<string, boolean>
  onToggleCategory: (cat: string) => void
  onSelectDate: (date: string) => void
  onSelectSchedule: (s: Schedule) => void
  searchInputRef: React.RefObject<HTMLInputElement | null>
  addToast: (type: 'success' | 'error' | 'info', message: string) => void
}

export function Sidebar({
  year,
  month,
  selectedDate,
  schedules,
  enabledCategories,
  onToggleCategory,
  onSelectDate,
  onSelectSchedule,
  searchInputRef,
  addToast,
}: Props) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Schedule[]>([])
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([])
      return
    }

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const results = await api.search(searchQuery.trim())
        setSearchResults(results)
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 300)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [searchQuery])

  const handleSelectResult = (s: Schedule) => {
    onSelectSchedule(s)
    const date = s.start_at.slice(0, 10)
    onSelectDate(date)
    setSearchQuery('')
    setSearchResults([])
  }

  return (
    <aside className="w-64 shrink-0 space-y-5">
      {/* Search */}
      <div className="relative">
        <div className="relative">
          <input
            ref={searchInputRef}
            type="text"
            placeholder="일정 검색... ( / )"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm focus:border-blue-500 focus:outline-none placeholder-slate-500"
          />
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
        {(searchResults.length > 0 || searching) && searchQuery.trim() && (
          <SearchResults
            results={searchResults}
            loading={searching}
            query={searchQuery}
            onSelect={handleSelectResult}
            onClose={() => { setSearchQuery(''); setSearchResults([]) }}
          />
        )}
      </div>

      {/* Mini Calendar */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3">
        <MiniCalendar
          year={year}
          month={month}
          selectedDate={selectedDate}
          schedules={schedules}
          onSelectDate={onSelectDate}
        />
      </div>

      {/* Category Filters */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">카테고리</h3>
        <div className="space-y-1.5">
          {Object.entries(CATEGORIES).map(([key, val]) => {
            const enabled = enabledCategories[key] !== false
            return (
              <button
                key={key}
                onClick={() => onToggleCategory(key)}
                className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-sm transition-colors ${
                  enabled ? 'hover:bg-slate-700/50' : 'opacity-40 hover:opacity-60'
                }`}
              >
                <span
                  className={`w-3 h-3 rounded-sm border-2 flex items-center justify-center transition-colors ${
                    enabled ? val.bg + ' border-current ' + val.color : 'border-slate-600'
                  }`}
                >
                  {enabled && <span className="text-[8px]">✓</span>}
                </span>
                <span className={enabled ? val.color : 'text-slate-500'}>{val.label}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Challenge Card */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3">
        <ChallengeCard addToast={addToast} />
      </div>

      {/* Keyboard shortcuts hint */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">단축키</h3>
        <div className="space-y-1 text-xs text-slate-500">
          <div className="flex justify-between">
            <span>새 일정</span>
            <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-slate-400">N</kbd>
          </div>
          <div className="flex justify-between">
            <span>오늘</span>
            <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-slate-400">T</kbd>
          </div>
          <div className="flex justify-between">
            <span>이전/다음</span>
            <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-slate-400">← →</kbd>
          </div>
          <div className="flex justify-between">
            <span>뷰 전환</span>
            <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-slate-400">1 2 3</kbd>
          </div>
          <div className="flex justify-between">
            <span>검색</span>
            <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-slate-400">/</kbd>
          </div>
        </div>
      </div>
    </aside>
  )
}
