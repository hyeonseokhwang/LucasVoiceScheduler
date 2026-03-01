import { useState, useEffect, useCallback } from 'react'
import type { Challenge } from '../types'
import { api } from '../lib/api'

interface Props {
  addToast: (type: 'success' | 'error' | 'info', message: string) => void
}

export function ChallengeCard({ addToast }: Props) {
  const [challenges, setChallenges] = useState<Challenge[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  const [showEarningForm, setShowEarningForm] = useState(false)
  const [earningAmount, setEarningAmount] = useState('')
  const [earningSource, setEarningSource] = useState('')
  const [earningNote, setEarningNote] = useState('')

  const fetchChallenges = useCallback(async () => {
    try {
      const list = await api.challengeList()
      // Fetch details for each to get progress
      const detailed = await Promise.all(list.map((c) => api.challengeGet(c.id)))
      setChallenges(detailed)
      if (detailed.length > 0 && expanded === null) {
        setExpanded(detailed[0].id)
      }
    } catch {
      // API might not be available yet
    }
  }, [expanded])

  useEffect(() => {
    fetchChallenges()
  }, [fetchChallenges])

  const handleAddEarning = async (challengeId: number) => {
    const amount = parseInt(earningAmount)
    if (!amount || amount <= 0) {
      addToast('error', '금액을 입력해주세요')
      return
    }
    try {
      await api.challengeAddEarning(challengeId, {
        amount,
        source: earningSource || undefined,
        note: earningNote || undefined,
      })
      addToast('success', `${amount.toLocaleString()}원 수익이 기록되었습니다`)
      setEarningAmount('')
      setEarningSource('')
      setEarningNote('')
      setShowEarningForm(false)
      fetchChallenges()
    } catch {
      addToast('error', '수익 기록에 실패했습니다')
    }
  }

  const handleToggleMilestone = async (challengeId: number, index: number, currentStatus: string) => {
    const newStatus = currentStatus === 'completed' ? 'pending' : 'completed'
    try {
      await api.challengeUpdateMilestone(challengeId, index, newStatus)
      fetchChallenges()
    } catch {
      addToast('error', '마일스톤 업데이트에 실패했습니다')
    }
  }

  if (challenges.length === 0) return null

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">챌린지</h3>
      {challenges.map((ch) => {
        const isExpanded = expanded === ch.id
        const pct = ch.progress?.percentage ?? 0
        const dDay = ch.progress?.d_day
        const milestones = ch.milestones || []
        const earnings = ch.earnings || []

        return (
          <div
            key={ch.id}
            className="bg-slate-800/80 rounded-xl border border-slate-700/50 overflow-hidden"
          >
            {/* Header */}
            <button
              onClick={() => setExpanded(isExpanded ? null : ch.id)}
              className="w-full p-3 text-left hover:bg-slate-700/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-amber-400">{ch.title}</span>
                {dDay !== null && dDay !== undefined && (
                  <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${
                    dDay <= 7 ? 'bg-red-500/20 text-red-400' :
                    dDay <= 30 ? 'bg-amber-500/20 text-amber-400' :
                    'bg-green-500/20 text-green-400'
                  }`}>
                    {dDay > 0 ? `D-${dDay}` : dDay === 0 ? 'D-Day' : `D+${Math.abs(dDay)}`}
                  </span>
                )}
              </div>

              {/* Progress bar */}
              <div className="relative h-2.5 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${
                    pct >= 100 ? 'bg-green-500' :
                    pct >= 50 ? 'bg-amber-500' :
                    'bg-blue-500'
                  }`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <div className="flex justify-between mt-1.5 text-xs text-slate-500">
                {ch.target_amount > 0 ? (
                  <>
                    <span>{ch.current_amount.toLocaleString()}원</span>
                    <span>{pct}%</span>
                    <span>{ch.target_amount.toLocaleString()}원</span>
                  </>
                ) : (
                  <>
                    <span>마일스톤 {ch.progress?.milestones_done ?? 0}/{ch.progress?.milestones_total ?? 0}</span>
                    <span>{pct}%</span>
                    <span>{ch.progress?.remaining ?? 0}개 남음</span>
                  </>
                )}
              </div>
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div className="border-t border-slate-700/50 p-3 space-y-3 animate-fade-in">
                {ch.description && (
                  <p className="text-xs text-slate-400">{ch.description}</p>
                )}

                {/* Milestone Timeline */}
                {milestones.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-slate-400 mb-2">마일스톤</h4>
                    <div className="space-y-1.5">
                      {milestones.map((ms, i) => {
                        const isDone = ms.status === 'completed'
                        const isPast = new Date(ms.due_date) < new Date()
                        return (
                          <button
                            key={i}
                            onClick={() => handleToggleMilestone(ch.id, i, ms.status)}
                            className="w-full flex items-center gap-2 text-left hover:bg-slate-700/30 rounded px-1 py-0.5 transition-colors"
                          >
                            <span className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${
                              isDone ? 'border-green-500 bg-green-500/20' :
                              isPast ? 'border-red-500 bg-red-500/10' :
                              'border-slate-600'
                            }`}>
                              {isDone && <span className="text-[8px] text-green-400">✓</span>}
                            </span>
                            <span className={`text-xs flex-1 ${isDone ? 'text-slate-500 line-through' : 'text-slate-300'}`}>
                              {ms.title}
                            </span>
                            <span className={`text-[10px] ${isPast && !isDone ? 'text-red-400' : 'text-slate-600'}`}>
                              {ms.due_date.slice(5)}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Earnings History (mini graph) */}
                {earnings.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-slate-400 mb-2">수익 기록</h4>
                    <div className="flex items-end gap-0.5 h-12 mb-1">
                      {earnings.map((e) => {
                        const maxAmt = Math.max(...earnings.map((x) => x.amount))
                        const h = maxAmt > 0 ? (e.amount / maxAmt) * 100 : 0
                        return (
                          <div
                            key={e.id}
                            className="flex-1 bg-amber-500/60 rounded-t hover:bg-amber-400/80 transition-colors group relative"
                            style={{ height: `${Math.max(h, 8)}%` }}
                            title={`${e.date}: ${e.amount.toLocaleString()}원${e.source ? ` (${e.source})` : ''}`}
                          />
                        )
                      })}
                    </div>
                    <div className="space-y-0.5">
                      {earnings.slice(-3).map((e) => (
                        <div key={e.id} className="flex justify-between text-[10px] text-slate-500">
                          <span>{e.date.slice(5)} {e.source && `· ${e.source}`}</span>
                          <span className="text-amber-400">+{e.amount.toLocaleString()}원</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Add earning button/form */}
                {!showEarningForm ? (
                  <button
                    onClick={() => setShowEarningForm(true)}
                    className="w-full py-1.5 text-xs text-amber-400 hover:bg-amber-500/10 rounded-lg border border-dashed border-amber-500/30 transition-colors"
                  >
                    + 수익 기록 추가
                  </button>
                ) : (
                  <div className="space-y-2 p-2 bg-slate-900/50 rounded-lg border border-slate-700/50">
                    <input
                      type="number"
                      placeholder="금액 (원)"
                      value={earningAmount}
                      onChange={(e) => setEarningAmount(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs focus:border-amber-500 focus:outline-none"
                      autoFocus
                    />
                    <input
                      type="text"
                      placeholder="출처 (예: 앱스토어, 광고)"
                      value={earningSource}
                      onChange={(e) => setEarningSource(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs focus:border-amber-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      placeholder="메모 (선택)"
                      value={earningNote}
                      onChange={(e) => setEarningNote(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs focus:border-amber-500 focus:outline-none"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleAddEarning(ch.id)}
                        className="flex-1 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 rounded font-medium transition-colors"
                      >
                        기록
                      </button>
                      <button
                        onClick={() => { setShowEarningForm(false); setEarningAmount(''); setEarningSource(''); setEarningNote('') }}
                        className="px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-700 rounded transition-colors"
                      >
                        취소
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
