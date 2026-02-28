import { useEffect, useRef, useCallback, useState } from 'react'
import type { Schedule } from '../types'

interface ReminderMessage {
  type: 'reminder'
  schedule: Schedule
}

export function useWebSocket(onReminder: (schedule: Schedule) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/schedules/ws`)

    ws.onopen = () => setConnected(true)

    ws.onmessage = (event) => {
      try {
        const msg: ReminderMessage = JSON.parse(event.data)
        if (msg.type === 'reminder') {
          onReminder(msg.schedule)
          // Browser notification
          if (Notification.permission === 'granted') {
            new Notification(`일정 알림: ${msg.schedule.title}`, {
              body: msg.schedule.description || '',
              icon: '/favicon.ico',
            })
          }
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onclose = () => {
      setConnected(false)
      setTimeout(connect, 3000) // auto-reconnect
    }

    wsRef.current = ws
  }, [onReminder])

  useEffect(() => {
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
    connect()
    return () => { wsRef.current?.close() }
  }, [connect])

  return { connected }
}
