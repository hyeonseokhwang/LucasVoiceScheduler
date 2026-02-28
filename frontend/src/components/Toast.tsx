import { useEffect } from 'react'

export interface ToastItem {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
  action?: () => void
  actionLabel?: string
  duration?: number
}

interface Props {
  toasts: ToastItem[]
  onRemove: (id: string) => void
}

export function Toast({ toasts, onRemove }: Props) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none">
      {toasts.map((toast) => (
        <ToastEntry key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  )
}

function ToastEntry({ toast, onRemove }: { toast: ToastItem; onRemove: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onRemove(toast.id), toast.duration || 4000)
    return () => clearTimeout(timer)
  }, [toast.id, toast.duration, onRemove])

  const colors: Record<string, string> = {
    success: 'bg-green-600/90 border-green-500/50',
    error: 'bg-red-600/90 border-red-500/50',
    info: 'bg-blue-600/90 border-blue-500/50',
  }

  const icons: Record<string, string> = {
    success: '✓',
    error: '✕',
    info: 'ℹ',
  }

  return (
    <div
      className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg border shadow-lg backdrop-blur-sm animate-toast-in ${colors[toast.type]}`}
    >
      <span className="text-lg leading-none">{icons[toast.type]}</span>
      <span className="text-sm font-medium">{toast.message}</span>
      {toast.action && (
        <button
          onClick={() => {
            toast.action?.()
            onRemove(toast.id)
          }}
          className="ml-1 px-2 py-0.5 bg-white/20 hover:bg-white/30 rounded text-xs font-bold transition-colors"
        >
          {toast.actionLabel || '되돌리기'}
        </button>
      )}
      <button
        onClick={() => onRemove(toast.id)}
        className="ml-1 text-white/60 hover:text-white text-sm"
      >
        ✕
      </button>
    </div>
  )
}
