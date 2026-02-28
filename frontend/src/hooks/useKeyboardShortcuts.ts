import { useEffect } from 'react'
import type { ViewMode } from '../types'

interface Handlers {
  onNewSchedule: () => void
  onToday: () => void
  onPrev: () => void
  onNext: () => void
  onSetView: (view: ViewMode) => void
  onFocusSearch: () => void
  isModalOpen: boolean
}

export function useKeyboardShortcuts({
  onNewSchedule,
  onToday,
  onPrev,
  onNext,
  onSetView,
  onFocusSearch,
  isModalOpen,
}: Handlers) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const isInput =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable

      // Esc always works
      if (e.key === 'Escape') return // handled by modal components directly

      // Don't intercept when typing in inputs (except / for search)
      if (isInput && e.key !== '/') return

      // Don't intercept when modal is open
      if (isModalOpen) return

      switch (e.key) {
        case 'n':
        case 'N':
          e.preventDefault()
          onNewSchedule()
          break
        case 't':
        case 'T':
          e.preventDefault()
          onToday()
          break
        case 'ArrowLeft':
          e.preventDefault()
          onPrev()
          break
        case 'ArrowRight':
          e.preventDefault()
          onNext()
          break
        case '1':
          e.preventDefault()
          onSetView('month')
          break
        case '2':
          e.preventDefault()
          onSetView('week')
          break
        case '3':
          e.preventDefault()
          onSetView('day')
          break
        case '/':
          e.preventDefault()
          onFocusSearch()
          break
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onNewSchedule, onToday, onPrev, onNext, onSetView, onFocusSearch, isModalOpen])
}
