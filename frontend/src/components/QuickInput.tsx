import { useState, useRef } from 'react'
import type { Schedule } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'

interface Props {
  onScheduleCreated: () => void
  addToast: (type: 'success' | 'error' | 'info', message: string) => void
}

interface ParseResult {
  parsed: {
    title: string
    start_at: string
    end_at?: string
    all_day?: boolean
    category?: string
  }
  confidence: number
  response: string
  conflicts: Schedule[]
}

export function QuickInput({ onScheduleCreated, addToast }: Props) {
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<ParseResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!value.trim() || loading) return

    setLoading(true)
    try {
      const result = await api.voiceParse(value.trim())
      setPreview(result)
    } catch {
      addToast('error', '자연어 파싱 실패')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async () => {
    if (!preview?.parsed) return
    setLoading(true)
    try {
      await api.voiceConfirm({
        title: preview.parsed.title,
        start_at: preview.parsed.start_at,
        end_at: preview.parsed.end_at,
        all_day: preview.parsed.all_day || false,
        category: preview.parsed.category || 'general',
      })
      addToast('success', `'${preview.parsed.title}' 생성 완료`)
      onScheduleCreated()
      handleCancel()
    } catch {
      addToast('error', '일정 생성 실패')
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = () => {
    setPreview(null)
    setValue('')
    inputRef.current?.blur()
  }

  const formatTime = (s: string) => {
    try {
      const d = new Date(s)
      return d.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    } catch {
      return s
    }
  }

  return (
    <div className="relative">
      <form onSubmit={handleSubmit} className="flex items-center">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text"
            placeholder="자연어로 입력 — 예: 내일 점심 회의"
            value={value}
            onChange={(e) => { setValue(e.target.value); setPreview(null) }}
            className="w-full bg-slate-800/80 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm focus:border-blue-500 focus:outline-none placeholder-slate-500 min-h-[40px]"
            disabled={loading}
          />
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        {value.trim() && !preview && (
          <button
            type="submit"
            disabled={loading}
            className="ml-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors min-h-[40px]"
          >
            {loading ? (
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : '파싱'}
          </button>
        )}
      </form>

      {/* Preview dropdown */}
      {preview && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-30 animate-fade-in">
          <div className="p-3 space-y-2">
            {/* AI response */}
            <p className="text-xs text-blue-400">{preview.response}</p>

            {/* Parsed info */}
            <div className="flex items-center gap-2 text-sm">
              <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                CATEGORIES[preview.parsed.category || 'general']?.bg || ''
              } ${CATEGORIES[preview.parsed.category || 'general']?.color || ''}`}>
                {CATEGORIES[preview.parsed.category || 'general']?.label || '일반'}
              </span>
              <span className="font-medium">{preview.parsed.title}</span>
              <span className="text-xs text-slate-500">{formatTime(preview.parsed.start_at)}</span>
            </div>

            {/* Conflicts */}
            {preview.conflicts.length > 0 && (
              <div className="text-xs text-yellow-400">
                ⚠ {preview.conflicts.length}개 일정과 시간이 겹칩니다
              </div>
            )}

            {/* Buttons */}
            <div className="flex gap-2">
              <button
                onClick={handleConfirm}
                disabled={loading}
                className="flex-1 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-md text-xs font-medium transition-colors"
              >
                생성
              </button>
              <button
                onClick={handleCancel}
                className="flex-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-md text-xs font-medium transition-colors"
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
