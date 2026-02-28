import type { Schedule } from '../types'
import { CATEGORIES } from '../types'

interface Props {
  results: Schedule[]
  loading: boolean
  query: string
  onSelect: (s: Schedule) => void
  onClose: () => void
}

function highlightMatch(text: string, query: string) {
  if (!query.trim()) return text
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-500/30 text-yellow-300 rounded px-0.5">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}

export function SearchResults({ results, loading, query, onSelect, onClose }: Props) {
  return (
    <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden z-30 max-h-80 overflow-y-auto">
      {loading && (
        <div className="px-3 py-4 text-center text-sm text-slate-500">
          <span className="inline-block animate-spin mr-2">⟳</span>검색 중...
        </div>
      )}

      {!loading && results.length === 0 && (
        <div className="px-3 py-4 text-center text-sm text-slate-500">
          "{query}"에 대한 결과가 없습니다
        </div>
      )}

      {!loading &&
        results.map((s) => {
          const cat = CATEGORIES[s.category] || CATEGORIES.general
          const date = new Date(s.start_at)
          const dateStr = date.toLocaleDateString('ko-KR', {
            month: 'short',
            day: 'numeric',
            weekday: 'short',
          })
          const timeStr = s.all_day
            ? '종일'
            : date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })

          return (
            <button
              key={`${s.id}-${s.start_at}`}
              onClick={() => onSelect(s)}
              className="w-full text-left px-3 py-2.5 hover:bg-slate-700/60 transition-colors border-b border-slate-700/50 last:border-b-0"
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`w-2 h-2 rounded-full ${cat.bg.split(' ')[0]}`} />
                <span className="text-sm font-medium truncate">
                  {highlightMatch(s.title, query)}
                </span>
              </div>
              <div className="text-xs text-slate-500 ml-4">
                {dateStr} {timeStr}
              </div>
              {s.description && (
                <div className="text-xs text-slate-600 ml-4 truncate mt-0.5">
                  {highlightMatch(s.description, query)}
                </div>
              )}
            </button>
          )
        })}

      {results.length > 0 && (
        <div className="px-3 py-2 text-center border-t border-slate-700/50">
          <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-400">
            닫기
          </button>
        </div>
      )}
    </div>
  )
}
