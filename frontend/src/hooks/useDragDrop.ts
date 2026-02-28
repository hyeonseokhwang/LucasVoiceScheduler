import { useState, useCallback, useRef } from 'react'
import type { Schedule } from '../types'
import { api } from '../lib/api'

interface UseDragDropReturn {
  dragging: Schedule | null
  dragOverTarget: string | null
  handleDragStart: (e: React.DragEvent, schedule: Schedule) => void
  handleDragOver: (e: React.DragEvent, targetId: string) => void
  handleDragLeave: () => void
  handleDrop: (e: React.DragEvent, date: string, hour?: number) => void
  handleDragEnd: () => void
}

interface Options {
  onMoved: () => void
  onOptimisticUpdate: (schedule: Schedule, newStartAt: string, newEndAt: string | null) => void
  addToast: (type: 'success' | 'error' | 'info', message: string) => void
}

export function useDragDrop({ onMoved, onOptimisticUpdate, addToast }: Options): UseDragDropReturn {
  const [dragging, setDragging] = useState<Schedule | null>(null)
  const [dragOverTarget, setDragOverTarget] = useState<string | null>(null)
  const draggingRef = useRef<Schedule | null>(null)

  const handleDragStart = useCallback((e: React.DragEvent, schedule: Schedule) => {
    // Don't allow dragging occurrence instances directly (they don't have real IDs to update)
    if (schedule._is_occurrence) {
      e.preventDefault()
      return
    }
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(schedule.id))
    setDragging(schedule)
    draggingRef.current = schedule
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent, targetId: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverTarget(targetId)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDragOverTarget(null)
  }, [])

  const handleDrop = useCallback(
    async (e: React.DragEvent, date: string, hour?: number) => {
      e.preventDefault()
      setDragOverTarget(null)

      const schedule = draggingRef.current
      if (!schedule) return

      const oldStart = new Date(schedule.start_at)
      const newStart = new Date(date)

      if (hour !== undefined) {
        newStart.setHours(hour, oldStart.getMinutes(), 0, 0)
      } else {
        newStart.setHours(oldStart.getHours(), oldStart.getMinutes(), 0, 0)
      }

      // Calculate new end if exists
      let newEnd: Date | null = null
      if (schedule.end_at) {
        const oldEnd = new Date(schedule.end_at)
        const duration = oldEnd.getTime() - oldStart.getTime()
        newEnd = new Date(newStart.getTime() + duration)
      }

      const newStartAt = formatLocalISO(newStart)
      const newEndAt = newEnd ? formatLocalISO(newEnd) : null

      // Skip if same time
      if (newStartAt === schedule.start_at.slice(0, 16)) {
        setDragging(null)
        draggingRef.current = null
        return
      }

      // Optimistic update
      onOptimisticUpdate(schedule, newStartAt, newEndAt)

      try {
        await api.update(schedule.id, {
          start_at: newStartAt,
          end_at: newEndAt || undefined,
        })
        addToast('success', `"${schedule.title}" 이동 완료`)
        onMoved()
      } catch {
        addToast('error', '일정 이동 실패')
        onMoved() // refetch to revert
      }

      setDragging(null)
      draggingRef.current = null
    },
    [onMoved, onOptimisticUpdate, addToast],
  )

  const handleDragEnd = useCallback(() => {
    setDragging(null)
    setDragOverTarget(null)
    draggingRef.current = null
  }, [])

  return {
    dragging,
    dragOverTarget,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
  }
}

function formatLocalISO(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day}T${h}:${min}`
}
