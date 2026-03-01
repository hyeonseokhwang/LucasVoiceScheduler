import { useState, useEffect, useCallback, useRef } from 'react'
import type { Schedule, ScheduleFormData } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'
import { useSpeechRecognition, speak, stopSpeaking, isSentenceEnd, enqueueTTS, onTTSQueueDone, resetTTSQueue } from '../hooks/useSpeechRecognition'

/** 화면 표시 + TTS 전송 전에 ACTION 태그/JSON/에러코드 제거 */
function cleanLLMText(text: string): string {
  return text
    // [ACTION:XXX] + 선택적 JSON
    .replace(/\[ACTION:\w+\]\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})?/g, '')
    // 잔여 대괄호 태그 [SOMETHING:SOMETHING]
    .replace(/\[[A-Z_]+(?::[A-Z_]+)*\]/g, '')
    // JSON 객체
    .replace(/\{[^{}]*"[^"]*"\s*:[^{}]*\}/g, '')
    // 에러 문자열
    .replace(/\b(UNDEFINED|UNPARSED\s*TEXT|undefined|null|NaN)\b/gi, '')
    // 연속 공백 정리
    .replace(/\s+/g, ' ')
    .trim()
}

interface Props {
  onScheduleCreated: () => void
  addToast: (type: 'success' | 'error' | 'info', message: string) => void
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  scheduleData?: Record<string, unknown> | null
  action?: string
}

type VoiceMode = 'closed' | 'idle' | 'listening' | 'processing' | 'speaking'

export function VoiceAssistant({ onScheduleCreated, addToast }: Props) {
  const [isOpen, setIsOpen] = useState(false)
  const [mode, setMode] = useState<VoiceMode>('closed')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [textInput, setTextInput] = useState('')
  const [conversationMode, setConversationMode] = useState(false)
  const [pendingSchedule, setPendingSchedule] = useState<Record<string, unknown> | null>(null)

  const chatEndRef = useRef<HTMLDivElement>(null)
  const lastTranscriptRef = useRef('')

  const { isListening, transcript, interimTranscript, isSupported, start, stop, reset, audioLevel, isLocal } =
    useSpeechRecognition()

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // When transcript changes (final result), process it
  useEffect(() => {
    if (transcript && transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript
      if (conversationMode || mode === 'listening') {
        stop()
        handleChat(transcript)
        reset()
      }
    }
  }, [transcript])

  // Sync listening state
  useEffect(() => {
    if (isListening && mode !== 'processing' && mode !== 'speaking') {
      setMode('listening')
    }
  }, [isListening])

  const handleChat = async (text: string) => {
    if (!text.trim()) return

    const userMsg: ChatMessage = { role: 'user', content: text, timestamp: new Date() }
    setMessages((prev) => [...prev, userMsg])
    setMode('processing')

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }))

      // SSE 스트리밍으로 실시간 응답 표시
      const resp = await fetch('/api/voice/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, history }),
      })

      if (!resp.ok || !resp.body) {
        // 스트리밍 실패 시 일반 호출 폴백
        const fallback = await fetch('/api/voice/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, history }),
        })
        const data = await fallback.json()
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: cleanLLMText(data.response) || '잘 못 알아들었어, 다시 말해줘.',
          timestamp: new Date(),
          scheduleData: data.schedule_data,
          action: data.action,
        }
        setMessages((prev) => [...prev, assistantMsg])
        if (data.action === 'CREATE' && data.schedule_data) {
          setPendingSchedule(data.schedule_data)
        }
        setMode('speaking')
        speak(assistantMsg.content, () => {
          if (conversationMode) {
            setMode('listening')
            reset()
            lastTranscriptRef.current = ''
            start()
          } else {
            setMode('idle')
          }
        })
        return
      }

      // 스트리밍 처리: 토큰 하나씩 표시 + 문장 단위 실시간 TTS
      const placeholderMsg: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, placeholderMsg])
      setMode('speaking')

      // 문장 단위 TTS 큐 초기화
      resetTTSQueue()

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ''
      let sentenceBuffer = '' // 현재 문장 누적 버퍼
      let lastFlushTime = Date.now()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        // SSE 형식: "data: ...\n\n"
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6)
            if (payload === '[DONE]') continue
            fullText += payload
            sentenceBuffer += payload

            const now = Date.now()
            // 문장 끝 감지 또는 3초 이상 버퍼에 쌓이면 강제 플러시
            const shouldFlush = isSentenceEnd(sentenceBuffer) ||
              (sentenceBuffer.trim().length > 15 && now - lastFlushTime > 3000)

            if (shouldFlush && sentenceBuffer.trim()) {
              const cleaned = cleanLLMText(sentenceBuffer)
              if (cleaned) enqueueTTS(cleaned)
              sentenceBuffer = ''
              lastFlushTime = now
            }

            // 화면에는 ACTION 태그 제거된 텍스트만 표시
            const displayText = cleanLLMText(fullText)
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: displayText }
              }
              return updated
            })
          }
        }
      }

      // 스트리밍 종료: 남은 버퍼도 TTS로 (클리닝 후)
      if (sentenceBuffer.trim()) {
        const cleaned = cleanLLMText(sentenceBuffer)
        if (cleaned) enqueueTTS(cleaned)
      }

      // 최종 표시 텍스트도 클리닝
      const finalDisplay = cleanLLMText(fullText)
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'assistant') {
          updated[updated.length - 1] = { ...last, content: finalDisplay || fullText }
        }
        return updated
      })

      if (!cleanLLMText(fullText).trim()) {
        fullText = '잘 못 알아들었어, 다시 말해줘.'
        speak(fullText, () => {
          if (conversationMode) {
            setMode('listening')
            reset()
            lastTranscriptRef.current = ''
            start()
          } else {
            setMode('idle')
          }
        })
      } else {
        // 모든 TTS 큐 재생 완료 후 콜백
        onTTSQueueDone(() => {
          if (conversationMode) {
            setMode('listening')
            reset()
            lastTranscriptRef.current = ''
            start()
          } else {
            setMode('idle')
          }
        })
      }
    } catch {
      const errMsg: ChatMessage = {
        role: 'assistant',
        content: '연결에 문제가 있어. 잠시 후 다시 시도해줘.',
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errMsg])
      setMode('idle')
    }
  }

  const handleConfirmSchedule = async () => {
    if (!pendingSchedule) return
    setMode('processing')
    try {
      await api.voiceConfirm(pendingSchedule as unknown as ScheduleFormData)
      const title = (pendingSchedule as Record<string, unknown>).title || '새 일정'
      const confirmMsg: ChatMessage = {
        role: 'assistant',
        content: `'${title}' 일정 생성 완료!`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, confirmMsg])
      speak(confirmMsg.content)
      addToast('success', `'${title}' 일정이 생성되었습니다`)
      onScheduleCreated()
      setPendingSchedule(null)
      setMode('idle')
    } catch {
      addToast('error', '일정 생성 실패')
      setMode('idle')
    }
  }

  const handleStartConversation = () => {
    setConversationMode(true)
    reset()
    lastTranscriptRef.current = ''
    start()
    if (messages.length === 0) {
      const greeting: ChatMessage = {
        role: 'assistant',
        content: '안녕, 루카스야. 무슨 일정을 도와줄까?',
        timestamp: new Date(),
      }
      setMessages([greeting])
      speak(greeting.content, () => {
        // Already listening via start()
      })
    }
  }

  const handleStopConversation = () => {
    setConversationMode(false)
    stop()
    stopSpeaking()
    setMode('idle')
  }

  const handleMicToggle = () => {
    if (isListening) {
      stop()
      if (transcript) {
        handleChat(transcript)
        reset()
      }
    } else {
      reset()
      lastTranscriptRef.current = ''
      start()
    }
  }

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!textInput.trim()) return
    handleChat(textInput.trim())
    setTextInput('')
  }

  const handleClose = () => {
    stop()
    stopSpeaking()
    setConversationMode(false)
    setMode('closed')
    setIsOpen(false)
  }

  const handleOpen = () => {
    setIsOpen(true)
    setMode('idle')
  }

  const formatTime = (d: Date) =>
    d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })

  const formatScheduleTime = (s: string) => {
    try {
      const d = new Date(s)
      return d.toLocaleString('ko-KR', { month: 'short', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit' })
    } catch {
      return s
    }
  }

  // FAB button
  if (!isOpen) {
    return (
      <button
        onClick={handleOpen}
        className="fixed bottom-6 right-6 w-14 h-14 bg-blue-600 hover:bg-blue-500 rounded-full shadow-lg shadow-blue-600/25 flex items-center justify-center transition-all hover:scale-110 z-30 group"
        title="음성비서 루카스"
      >
        <svg className="w-6 h-6 group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      </button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 w-[400px] max-w-[calc(100vw-2rem)] bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl z-30 animate-modal-in flex flex-col" style={{ maxHeight: '70vh' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50 shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full transition-colors ${
            mode === 'listening' ? 'bg-red-500 animate-pulse'
              : mode === 'speaking' ? 'bg-green-500 animate-pulse'
                : mode === 'processing' ? 'bg-yellow-500 animate-pulse'
                  : 'bg-slate-500'
          }`} />
          <h3 className="font-semibold text-sm">루카스</h3>
          <span className="text-[10px] text-slate-500 bg-slate-700 px-1.5 py-0.5 rounded">
            {mode === 'listening' ? '듣는 중' : mode === 'speaking' ? '말하는 중' : mode === 'processing' ? '생각 중' : 'AI 비서'}
          </span>
          {isLocal && (
            <span className="text-[9px] text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded" title="완전 로컬 처리 (Whisper)">
              LOCAL
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={conversationMode ? handleStopConversation : handleStartConversation}
            className={`px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
              conversationMode
                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                : 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
            }`}
            title={conversationMode ? '대화 중지' : '연속 대화'}
          >
            {conversationMode ? '대화 중지' : '대화 모드'}
          </button>
          <button onClick={handleClose} className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-700">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[200px]">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <div className="text-3xl mb-3 opacity-50">🎙️</div>
            <p className="text-sm text-slate-400 mb-1">음성비서 루카스</p>
            <p className="text-xs text-slate-500">
              {isLocal ? '완전 로컬 음성인식 (Whisper)' : '대화 모드를 시작하거나 텍스트를 입력하세요'}
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-md'
                  : 'bg-slate-700 text-slate-200 rounded-bl-md'
              }`}
            >
              <p className="text-sm leading-relaxed">{msg.content}</p>

              {msg.scheduleData && msg.action === 'CREATE' && (
                <div className="mt-2 p-2.5 bg-black/20 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      CATEGORIES[(msg.scheduleData as Record<string, string>).category || 'general']?.bg || 'bg-blue-500/20'
                    } ${CATEGORIES[(msg.scheduleData as Record<string, string>).category || 'general']?.color || 'text-blue-400'}`}>
                      {CATEGORIES[(msg.scheduleData as Record<string, string>).category || 'general']?.label || '일반'}
                    </span>
                    <span className="text-xs font-medium">{(msg.scheduleData as Record<string, string>).title}</span>
                  </div>
                  <div className="text-[11px] opacity-75">
                    {formatScheduleTime((msg.scheduleData as Record<string, string>).start_at)}
                  </div>
                </div>
              )}

              <div className="text-[10px] opacity-40 mt-1">{formatTime(msg.timestamp)}</div>
            </div>
          </div>
        ))}

        {/* Audio level visualization + interim transcript */}
        {mode === 'listening' && (
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-blue-600/30 text-blue-200 rounded-br-md border border-blue-500/30">
              {/* Audio waveform bars */}
              {isLocal && audioLevel > 0 && (
                <div className="flex items-end gap-0.5 h-6 mb-1.5 justify-center">
                  {Array.from({ length: 7 }).map((_, i) => {
                    const barLevel = Math.max(0.1, audioLevel * (0.3 + 0.7 * Math.sin((Date.now() / 150 + i * 0.8))))
                    return (
                      <div
                        key={i}
                        className="w-1 bg-blue-400 rounded-full transition-all duration-75"
                        style={{ height: `${Math.max(3, barLevel * 24)}px` }}
                      />
                    )
                  })}
                </div>
              )}
              <p className="text-sm italic">
                {interimTranscript ? (
                  <span className="opacity-60">{interimTranscript}</span>
                ) : transcript ? (
                  <span>{transcript}</span>
                ) : (
                  <span className="opacity-40">
                    {isLocal ? '말해보세요...' : '듣고 있어요...'}
                  </span>
                )}
              </p>
            </div>
          </div>
        )}

        {mode === 'processing' && (
          <div className="flex justify-start">
            <div className="bg-slate-700 rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex gap-1.5">
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        {pendingSchedule && mode !== 'processing' && (
          <div className="flex gap-2 justify-center animate-fade-in">
            <button
              onClick={handleConfirmSchedule}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium transition-colors"
            >
              생성 확인
            </button>
            <button
              onClick={() => {
                setPendingSchedule(null)
                const cancelMsg: ChatMessage = { role: 'assistant', content: '알겠어, 취소했어.', timestamp: new Date() }
                setMessages((prev) => [...prev, cancelMsg])
                speak(cancelMsg.content)
              }}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-xl text-sm font-medium transition-colors"
            >
              취소
            </button>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Bottom controls */}
      <div className="shrink-0 px-4 py-3 border-t border-slate-700/50 space-y-2">
        <form onSubmit={handleTextSubmit} className="flex gap-2">
          <input
            type="text"
            placeholder={conversationMode ? '음성으로 대화 중...' : '예: 내일 오후 3시에 팀 회의'}
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none placeholder-slate-500"
            disabled={mode === 'processing'}
          />
          {textInput.trim() ? (
            <button
              type="submit"
              disabled={mode === 'processing'}
              className="p-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-xl transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          ) : isSupported ? (
            <button
              type="button"
              onClick={handleMicToggle}
              disabled={mode === 'processing' || mode === 'speaking'}
              className={`relative p-2.5 rounded-xl transition-all ${
                isListening
                  ? 'bg-red-500 hover:bg-red-400 shadow-lg shadow-red-500/25'
                  : 'bg-slate-700 hover:bg-slate-600 disabled:opacity-50'
              }`}
              title={isListening ? '듣기 중지' : '음성 입력'}
            >
              {/* Audio level ring (local STT only) */}
              {isListening && isLocal && audioLevel > 0.05 && (
                <span
                  className="absolute inset-0 rounded-xl border-2 border-red-400 pointer-events-none"
                  style={{
                    transform: `scale(${1 + audioLevel * 0.3})`,
                    opacity: 0.4 + audioLevel * 0.6,
                    transition: 'transform 75ms, opacity 75ms',
                  }}
                />
              )}
              <svg className="w-4 h-4 relative" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </button>
          ) : null}
        </form>

        {!isSupported && (
          <p className="text-[10px] text-slate-500 text-center">
            마이크 접근 권한이 필요합니다.
          </p>
        )}
      </div>
    </div>
  )
}
