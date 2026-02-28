import { useState, useCallback, useRef, useEffect } from 'react'

// ─── Types ───

interface SpeechRecognitionResult {
  isListening: boolean
  transcript: string
  interimTranscript: string
  isSupported: boolean
  start: () => void
  stop: () => void
  reset: () => void
  /** Audio level 0-1 for visualization (local STT only) */
  audioLevel: number
  /** Whether using local Whisper STT */
  isLocal: boolean
  /** Start in continuous/conversation mode (with silence detection + auto-restart) */
  startContinuous?: () => void
}

interface SpeechRecognitionEvent {
  results: {
    [index: number]: {
      [index: number]: { transcript: string }
      isFinal: boolean
    }
    length: number
  }
}

interface SpeechRecognitionInstance {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onend: (() => void) | null
  onerror: ((event: { error: string }) => void) | null
  onstart: (() => void) | null
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognitionInstance
    webkitSpeechRecognition: new () => SpeechRecognitionInstance
  }
}

// ─── Local Whisper STT Hook ───
// Flow:
//   단일 모드: 마이크 클릭 → 녹음 → 다시 클릭 → Whisper 전송
//   대화 모드: 녹음 시작 → 침묵 감지 → 자동 전송 → 자동 재시작

const LOG_PREFIX = '[LocalSTT]'

export function useLocalSTT(): SpeechRecognitionResult {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [audioLevel, setAudioLevel] = useState(0)
  const [isSupported, setIsSupported] = useState(true)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animFrameRef = useRef<number>(0)
  const autoRestartRef = useRef(false)
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const audioContextRef = useRef<AudioContext | null>(null)
  const isRecordingRef = useRef(false)
  const continuousModeRef = useRef(false) // true = 대화 모드 (침묵 감지 ON)

  useEffect(() => {
    const supported = typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
    setIsSupported(supported)
    console.log(LOG_PREFIX, 'MediaRecorder supported:', supported)
    return () => {
      autoRestartRef.current = false
      isRecordingRef.current = false
      cleanupAll()
    }
  }, [])

  const cleanupAll = useCallback(() => {
    console.log(LOG_PREFIX, 'cleanupAll')
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop() } catch { /* ok */ }
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (audioContextRef.current) {
      try { audioContextRef.current.close() } catch { /* ok */ }
      audioContextRef.current = null
    }
    analyserRef.current = null
    mediaRecorderRef.current = null
    setAudioLevel(0)
  }, [])

  const sendToWhisper = useCallback(async (audioBlob: Blob): Promise<string> => {
    console.log(LOG_PREFIX, `sendToWhisper: blob size=${audioBlob.size} bytes`)

    if (audioBlob.size < 1000) {
      console.log(LOG_PREFIX, 'Audio too small, skipping')
      return ''
    }

    setInterimTranscript('인식 중...')
    try {
      const formData = new FormData()
      formData.append('audio', audioBlob, 'recording.webm')

      console.log(LOG_PREFIX, 'Sending to /api/voice/transcribe...')
      const res = await fetch('/api/voice/transcribe', {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      console.log(LOG_PREFIX, 'Whisper response:', JSON.stringify(data))

      if (data.text && data.text.trim()) {
        const text = data.text.trim()
        console.log(LOG_PREFIX, `Transcribed: "${text}" (${data.processing_time}s)`)
        setTranscript(text)
        setInterimTranscript('')
        return text
      } else if (data.error) {
        console.warn(LOG_PREFIX, 'Whisper error:', data.error)
        setInterimTranscript('')
        return ''
      } else {
        console.log(LOG_PREFIX, 'No speech detected in audio')
        setInterimTranscript('')
        return ''
      }
    } catch (err) {
      console.error(LOG_PREFIX, 'Whisper request failed:', err)
      setInterimTranscript('')
      return ''
    }
  }, [])

  const startRecording = useCallback(async (continuous: boolean) => {
    if (isRecordingRef.current) {
      console.log(LOG_PREFIX, 'Already recording, ignoring start')
      return
    }

    console.log(LOG_PREFIX, `startRecording(continuous=${continuous})`)
    continuousModeRef.current = continuous
    autoRestartRef.current = continuous

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      console.log(LOG_PREFIX, 'Microphone stream obtained')
      streamRef.current = stream
      isRecordingRef.current = true

      // Audio analyser
      const audioCtx = new AudioContext()
      audioContextRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.8
      source.connect(analyser)
      analyserRef.current = analyser

      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      const updateLevel = () => {
        if (!analyserRef.current) return
        analyserRef.current.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((sum, v) => sum + v, 0) / dataArray.length
        setAudioLevel(Math.min(avg / 128, 1))
        animFrameRef.current = requestAnimationFrame(updateLevel)
      }
      updateLevel()

      // MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      console.log(LOG_PREFIX, 'MediaRecorder mimeType:', mimeType)

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
          console.log(LOG_PREFIX, `Chunk received: ${e.data.size} bytes`)
        }
      }

      recorder.onstop = async () => {
        console.log(LOG_PREFIX, 'Recorder stopped, chunks:', chunksRef.current.length)
        isRecordingRef.current = false
        setIsListening(false)

        if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
        setAudioLevel(0)

        // Cleanup mic stream
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(t => t.stop())
          streamRef.current = null
        }
        if (audioContextRef.current) {
          try { audioContextRef.current.close() } catch { /* ok */ }
          audioContextRef.current = null
        }
        analyserRef.current = null

        // Send to Whisper
        if (chunksRef.current.length > 0) {
          const blob = new Blob(chunksRef.current, { type: mimeType })
          chunksRef.current = []
          console.log(LOG_PREFIX, `Sending ${blob.size} bytes to Whisper...`)
          await sendToWhisper(blob)
        }

        // Auto-restart only in conversation mode
        if (autoRestartRef.current && continuousModeRef.current) {
          console.log(LOG_PREFIX, 'Auto-restarting (conversation mode)')
          setTimeout(() => {
            if (autoRestartRef.current) startRecording(true)
          }, 500)
        }
      }

      recorder.start()
      setIsListening(true)
      console.log(LOG_PREFIX, 'Recording started')

      // Silence detection — ONLY in continuous/conversation mode
      if (continuous) {
        console.log(LOG_PREFIX, 'Silence detection enabled (conversation mode)')
        let lastSpeechTime = Date.now()
        let speechDetected = false
        const recordStart = Date.now()

        const checkSilence = () => {
          if (!isRecordingRef.current || !analyserRef.current) return

          analyserRef.current.getByteFrequencyData(dataArray)
          const avg = dataArray.reduce((sum, v) => sum + v, 0) / dataArray.length

          if (avg > 15) {
            lastSpeechTime = Date.now()
            if (!speechDetected) {
              console.log(LOG_PREFIX, 'Speech detected, avg level:', avg.toFixed(1))
              speechDetected = true
            }
          }

          const elapsed = Date.now() - recordStart
          const silenceDuration = Date.now() - lastSpeechTime

          // After speech → 2.5s silence → stop
          if (speechDetected && silenceDuration > 2500) {
            console.log(LOG_PREFIX, `Silence timeout after speech (${silenceDuration}ms), stopping`)
            if (mediaRecorderRef.current?.state === 'recording') {
              mediaRecorderRef.current.stop()
              return
            }
          }

          // No speech at all after 15s → stop
          if (!speechDetected && elapsed > 15000) {
            console.log(LOG_PREFIX, 'No speech detected for 15s, stopping')
            if (mediaRecorderRef.current?.state === 'recording') {
              mediaRecorderRef.current.stop()
              return
            }
          }

          // Max 30s
          if (elapsed > 30000) {
            console.log(LOG_PREFIX, 'Max recording time reached (30s), stopping')
            if (mediaRecorderRef.current?.state === 'recording') {
              mediaRecorderRef.current.stop()
              return
            }
          }

          silenceTimerRef.current = setTimeout(checkSilence, 200)
        }
        silenceTimerRef.current = setTimeout(checkSilence, 1500)
      } else {
        console.log(LOG_PREFIX, 'No silence detection (manual mode — click mic again to stop)')
      }

    } catch (err) {
      console.error(LOG_PREFIX, 'Failed to start recording:', err)
      isRecordingRef.current = false
      setIsListening(false)
      setIsSupported(false)
    }
  }, [sendToWhisper])

  // Public start — defaults to manual mode (no silence detection)
  const start = useCallback(() => {
    startRecording(false)
  }, [startRecording])

  // Public startContinuous — conversation mode with silence detection
  const startContinuous = useCallback(() => {
    startRecording(true)
  }, [startRecording])

  const stop = useCallback(() => {
    console.log(LOG_PREFIX, 'stop() called')
    autoRestartRef.current = false
    continuousModeRef.current = false
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
    if (mediaRecorderRef.current?.state === 'recording') {
      isRecordingRef.current = false
      mediaRecorderRef.current.stop()
    } else {
      isRecordingRef.current = false
      cleanupAll()
      setIsListening(false)
    }
  }, [cleanupAll])

  const reset = useCallback(() => {
    setTranscript('')
    setInterimTranscript('')
  }, [])

  return {
    isListening,
    transcript,
    interimTranscript,
    isSupported,
    start,
    stop,
    reset,
    audioLevel,
    isLocal: true,
    startContinuous,
  }
}

// ─── Browser Speech Recognition (fallback) ───

export function useBrowserSTT(): SpeechRecognitionResult {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const autoRestartRef = useRef(false)

  const SpeechRecognitionAPI =
    typeof window !== 'undefined'
      ? window.SpeechRecognition || window.webkitSpeechRecognition
      : null

  const isSupported = !!SpeechRecognitionAPI

  useEffect(() => {
    return () => {
      autoRestartRef.current = false
      if (recognitionRef.current) recognitionRef.current.abort()
    }
  }, [])

  const start = useCallback(() => {
    if (!SpeechRecognitionAPI) return
    if (recognitionRef.current) {
      try { recognitionRef.current.abort() } catch { /* ok */ }
    }

    const recognition = new SpeechRecognitionAPI()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'ko-KR'
    autoRestartRef.current = true

    recognition.onstart = () => setIsListening(true)

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let final = ''
      let interim = ''
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      if (final) setTranscript(final)
      setInterimTranscript(interim)
    }

    recognition.onerror = (event) => {
      if (event.error === 'aborted') return
      console.warn('Speech recognition error:', event.error)
      if (event.error !== 'no-speech') {
        setIsListening(false)
        autoRestartRef.current = false
      }
    }

    recognition.onend = () => {
      setIsListening(false)
      if (autoRestartRef.current && SpeechRecognitionAPI) {
        try {
          const next = new SpeechRecognitionAPI()
          next.continuous = true
          next.interimResults = true
          next.lang = 'ko-KR'
          next.onstart = recognition.onstart
          next.onresult = recognition.onresult
          next.onerror = recognition.onerror
          next.onend = recognition.onend
          recognitionRef.current = next
          setTimeout(() => {
            try { next.start() } catch { /* ignore */ }
          }, 100)
        } catch { /* ignore */ }
      }
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch (e) {
      console.warn('Failed to start speech recognition:', e)
    }
  }, [SpeechRecognitionAPI])

  const stop = useCallback(() => {
    autoRestartRef.current = false
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch { /* ok */ }
      recognitionRef.current = null
    }
    setIsListening(false)
  }, [])

  const reset = useCallback(() => {
    setTranscript('')
    setInterimTranscript('')
  }, [])

  return {
    isListening,
    transcript,
    interimTranscript,
    isSupported,
    start,
    stop,
    reset,
    audioLevel: 0,
    isLocal: false,
  }
}

// ─── Auto-select best STT ───
// Browser STT = 실시간 중간 텍스트, 즉시 동작 (Google 서버 경유)
// Local Whisper = 완전 로컬, 하지만 중간 텍스트 없음 (녹음 끝나야 결과)
// 기본: Browser STT (UX 우선). Whisper는 백엔드에 대기.

export function useSpeechRecognition(): SpeechRecognitionResult {
  const browser = useBrowserSTT()
  const local = useLocalSTT()

  // Browser STT가 지원되면 기본 사용 (실시간 피드백 제공)
  if (browser.isSupported) return { ...browser, startContinuous: local.startContinuous }
  // 미지원 시 Local Whisper 폴백
  return local
}

// ─── TTS Functions (Edge TTS via backend) ───

let currentAudio: HTMLAudioElement | null = null
let currentObjectUrl: string | null = null

export function speak(text: string, onEnd?: () => void): void {
  // 이전 재생 중지
  stopSpeaking()

  if (!text.trim()) {
    onEnd?.()
    return
  }

  // Edge TTS API 호출 → MP3 스트리밍 재생
  fetch('/api/voice/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
    .then((res) => {
      if (!res.ok) throw new Error('TTS failed')
      return res.blob()
    })
    .then((blob) => {
      if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl)
      currentObjectUrl = URL.createObjectURL(blob)
      const audio = new Audio(currentObjectUrl)
      currentAudio = audio
      audio.onended = () => {
        currentAudio = null
        if (currentObjectUrl) {
          URL.revokeObjectURL(currentObjectUrl)
          currentObjectUrl = null
        }
        onEnd?.()
      }
      audio.onerror = () => {
        currentAudio = null
        onEnd?.()
      }
      audio.play().catch(() => {
        // 자동 재생 차단 시 폴백: 브라우저 내장 TTS
        _fallbackSpeak(text, onEnd)
      })
    })
    .catch(() => {
      // Edge TTS 실패 시 브라우저 내장 TTS 폴백
      _fallbackSpeak(text, onEnd)
    })
}

export function stopSpeaking(): void {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.currentTime = 0
    currentAudio = null
  }
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl)
    currentObjectUrl = null
  }
  // 폴백 TTS도 중지
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
}

/** 브라우저 내장 TTS 폴백 (Edge TTS 실패 시) */
function _fallbackSpeak(text: string, onEnd?: () => void): void {
  if (!('speechSynthesis' in window)) {
    onEnd?.()
    return
  }
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'ko-KR'
  utterance.rate = 1.4
  if (onEnd) utterance.onend = () => onEnd()
  window.speechSynthesis.speak(utterance)
}
