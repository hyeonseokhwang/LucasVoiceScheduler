import { useState, useEffect, useCallback } from 'react'
import type { Challenge } from '../types'
import { api } from '../lib/api'

interface Props {
  addToast: (type: 'success' | 'error' | 'info', message: string) => void
}

export function ChallengePage({ addToast }: Props) {
  const [challenges, setChallenges] = useState<Challenge[]>([])
  const [selected, setSelected] = useState<Challenge | null>(null)
  const [loading, setLoading] = useState(true)

  // Earning form
  const [amount, setAmount] = useState('')
  const [source, setSource] = useState('')
  const [note, setNote] = useState('')

  const fetchChallenges = useCallback(async () => {
    setLoading(true)
    try {
      const list = await api.challengeList()
      const detailed = await Promise.all(list.map(c => api.challengeGet(c.id)))
      setChallenges(detailed)
      if (detailed.length > 0 && !selected) {
        setSelected(detailed[0])
      } else if (selected) {
        const updated = detailed.find(c => c.id === selected.id)
        if (updated) setSelected(updated)
      }
    } catch {
      addToast('error', '챌린지를 불러오지 못했습니다')
    } finally {
      setLoading(false)
    }
  }, [addToast, selected])

  useEffect(() => { fetchChallenges() }, []) // eslint-disable-line

  const handleAddEarning = async () => {
    if (!selected) return
    const amt = parseInt(amount)
    if (!amt || amt <= 0) {
      addToast('error', '금액을 입력해주세요')
      return
    }
    try {
      await api.challengeAddEarning(selected.id, { amount: amt, source: source || undefined, note: note || undefined })
      addToast('success', `${amt.toLocaleString()}원 수익 기록 완료`)
      setAmount(''); setSource(''); setNote('')
      fetchChallenges()
    } catch {
      addToast('error', '수익 기록 실패')
    }
  }

  const handleToggleMilestone = async (index: number, currentStatus: string) => {
    if (!selected) return
    const newStatus = currentStatus === 'completed' ? 'pending' : 'completed'
    try {
      await api.challengeUpdateMilestone(selected.id, index, newStatus)
      fetchChallenges()
    } catch {
      addToast('error', '마일스톤 업데이트 실패')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <svg className="animate-spin h-8 w-8 text-amber-500" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    )
  }

  if (challenges.length === 0) {
    return (
      <div className="text-center py-20">
        <div className="text-5xl mb-4 opacity-30">🎯</div>
        <p className="text-slate-500 text-lg">진행 중인 챌린지가 없습니다</p>
      </div>
    )
  }

  const ch = selected || challenges[0]
  const progress = ch.progress
  const milestones = ch.milestones || []
  const earnings = ch.earnings || []
  const pct = progress?.percentage ?? 0
  const dDay = progress?.d_day

  // Cumulative earnings for chart
  const cumulativeData = earnings.reduce<{ date: string; total: number }[]>((acc, e) => {
    const prev = acc.length > 0 ? acc[acc.length - 1].total : 0
    acc.push({ date: e.date, total: prev + e.amount })
    return acc
  }, [])

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Challenge selector (if multiple) */}
      {challenges.length > 1 && (
        <div className="flex gap-2">
          {challenges.map(c => (
            <button key={c.id}
              onClick={() => setSelected(c)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                c.id === ch.id ? 'bg-amber-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >{c.title}</button>
          ))}
        </div>
      )}

      {/* Hero card */}
      <div className="bg-gradient-to-br from-amber-900/30 to-slate-800 rounded-2xl border border-amber-500/20 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-amber-400">{ch.title}</h2>
            {ch.description && <p className="text-sm text-slate-400 mt-1">{ch.description}</p>}
          </div>
          {dDay !== null && dDay !== undefined && (
            <div className={`text-3xl font-bold font-mono ${
              dDay <= 7 ? 'text-red-400' : dDay <= 30 ? 'text-amber-400' : 'text-green-400'
            }`}>
              {dDay > 0 ? `D-${dDay}` : dDay === 0 ? 'D-Day!' : `D+${Math.abs(dDay)}`}
            </div>
          )}
        </div>

        {/* Big progress bar */}
        <div className="relative h-6 bg-slate-700/80 rounded-full overflow-hidden mb-2">
          <div
            className={`absolute inset-y-0 left-0 rounded-full transition-all duration-700 ${
              pct >= 100 ? 'bg-gradient-to-r from-green-600 to-green-400' :
              pct >= 50 ? 'bg-gradient-to-r from-amber-600 to-amber-400' :
              'bg-gradient-to-r from-blue-600 to-blue-400'
            }`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
          <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
            {pct}%
          </div>
        </div>
        <div className="flex justify-between text-sm">
          {ch.target_amount > 0 ? (
            <>
              <span className="text-slate-400">{ch.current_amount.toLocaleString()}원 달성</span>
              <span className="text-slate-500">목표 {ch.target_amount.toLocaleString()}원</span>
            </>
          ) : (
            <>
              <span className="text-slate-400">마일스톤 {progress?.milestones_done ?? 0}/{progress?.milestones_total ?? 0} 완료</span>
              <span className="text-slate-500">{progress?.remaining ?? 0}개 남음</span>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Chart + Earnings */}
        <div className="space-y-6">
          {/* Cumulative earnings line chart */}
          <div className="bg-slate-800/80 rounded-xl border border-slate-700/50 p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">수익 추이</h3>
            {cumulativeData.length > 0 ? (
              <div className="h-40">
                <EarningsChart data={cumulativeData} target={ch.target_amount} />
              </div>
            ) : (
              <div className="h-40 flex items-center justify-center text-slate-500 text-sm">
                아직 수익 기록이 없습니다
              </div>
            )}
          </div>

          {/* Earnings table */}
          <div className="bg-slate-800/80 rounded-xl border border-slate-700/50 p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">수익 기록</h3>
            {earnings.length > 0 ? (
              <div className="space-y-1 max-h-60 overflow-y-auto">
                {[...earnings].reverse().map(e => (
                  <div key={e.id} className="flex items-center justify-between py-1.5 px-2 hover:bg-slate-700/30 rounded">
                    <div>
                      <span className="text-xs text-slate-500">{e.date}</span>
                      {e.source && <span className="text-xs text-slate-400 ml-2">{e.source}</span>}
                      {e.note && <span className="text-[10px] text-slate-600 ml-2">{e.note}</span>}
                    </div>
                    <span className="text-sm font-medium text-amber-400">+{e.amount.toLocaleString()}원</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">아직 기록이 없습니다</p>
            )}

            {/* Add earning form */}
            <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-2">
              <div className="flex gap-2">
                <input type="number" placeholder="금액 (원)" value={amount} onChange={e => setAmount(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
                <input type="text" placeholder="출처" value={source} onChange={e => setSource(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
              </div>
              <div className="flex gap-2">
                <input type="text" placeholder="메모 (선택)" value={note} onChange={e => setNote(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
                <button onClick={handleAddEarning}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-lg text-sm font-medium transition-colors"
                >기록</button>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Milestones timeline */}
        <div className="bg-slate-800/80 rounded-xl border border-slate-700/50 p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">마일스톤 타임라인</h3>
          <MilestoneTimeline
            milestones={milestones}
            deadline={ch.deadline}
            createdAt={ch.created_at}
            onToggle={handleToggleMilestone}
          />
        </div>
      </div>
    </div>
  )
}

/** Simple SVG line chart for cumulative earnings */
function EarningsChart({ data, target }: { data: { date: string; total: number }[]; target: number }) {
  if (data.length === 0) return null

  const W = 400
  const H = 140
  const PAD = { top: 10, right: 10, bottom: 25, left: 50 }
  const chartW = W - PAD.left - PAD.right
  const chartH = H - PAD.top - PAD.bottom

  const maxVal = Math.max(target, ...data.map(d => d.total))

  const points = data.map((d, i) => ({
    x: PAD.left + (i / Math.max(data.length - 1, 1)) * chartW,
    y: PAD.top + chartH - (d.total / maxVal) * chartH,
  }))

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const areaD = pathD + ` L${points[points.length - 1].x},${PAD.top + chartH} L${points[0].x},${PAD.top + chartH} Z`

  const targetY = PAD.top + chartH - (target / maxVal) * chartH

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
      {/* Target line */}
      <line x1={PAD.left} y1={targetY} x2={W - PAD.right} y2={targetY}
        stroke="#f59e0b" strokeWidth="1" strokeDasharray="4 4" opacity="0.5" />
      <text x={PAD.left - 4} y={targetY + 3} textAnchor="end" fontSize="9" fill="#f59e0b" opacity="0.7">
        목표
      </text>

      {/* Area fill */}
      <path d={areaD} fill="url(#earningGrad)" opacity="0.3" />

      {/* Line */}
      <path d={pathD} fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinejoin="round" />

      {/* Data points */}
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#f59e0b" />
      ))}

      {/* X-axis labels */}
      {data.map((d, i) => {
        if (data.length > 7 && i % Math.ceil(data.length / 7) !== 0 && i !== data.length - 1) return null
        return (
          <text key={i} x={points[i].x} y={H - 5} textAnchor="middle" fontSize="9" fill="#64748b">
            {d.date.slice(5)}
          </text>
        )
      })}

      {/* Y-axis labels */}
      {[0, 0.5, 1].map(frac => {
        const val = Math.round(maxVal * frac)
        const y = PAD.top + chartH - frac * chartH
        return (
          <text key={frac} x={PAD.left - 4} y={y + 3} textAnchor="end" fontSize="9" fill="#64748b">
            {val >= 10000 ? `${Math.round(val / 10000)}만` : val >= 1000 ? `${(val / 1000).toFixed(0)}천` : val}
          </text>
        )
      })}

      <defs>
        <linearGradient id="earningGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  )
}

/** Gantt-style milestone timeline */
function MilestoneTimeline({ milestones, deadline, createdAt, onToggle }: {
  milestones: { title: string; due_date: string; status: string }[]
  deadline: string
  createdAt: string
  onToggle: (index: number, status: string) => void
}) {
  const now = new Date()
  const start = new Date(createdAt)
  const end = new Date(deadline)
  const totalDays = Math.max((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24), 1)
  const elapsedDays = (now.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
  const elapsedPct = Math.min(Math.max(elapsedDays / totalDays * 100, 0), 100)

  return (
    <div className="space-y-6">
      {/* Overall timeline bar */}
      <div>
        <div className="flex justify-between text-[10px] text-slate-500 mb-1">
          <span>{createdAt.slice(0, 10)}</span>
          <span>{deadline}</span>
        </div>
        <div className="relative h-3 bg-slate-700 rounded-full overflow-hidden">
          <div className="absolute inset-y-0 left-0 bg-amber-500/40 rounded-full" style={{ width: `${elapsedPct}%` }} />
          {/* Milestone markers on the bar */}
          {milestones.map((ms, i) => {
            const msDate = new Date(ms.due_date)
            const msDays = (msDate.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
            const msPct = (msDays / totalDays) * 100
            return (
              <div key={i}
                className={`absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border-2 ${
                  ms.status === 'completed' ? 'bg-green-500 border-green-400' :
                  new Date(ms.due_date) < now ? 'bg-red-500 border-red-400' :
                  'bg-slate-600 border-slate-500'
                }`}
                style={{ left: `calc(${msPct}% - 5px)` }}
                title={ms.title}
              />
            )
          })}
          {/* Now marker */}
          <div className="absolute top-0 bottom-0 w-0.5 bg-white/70" style={{ left: `${elapsedPct}%` }} />
        </div>
      </div>

      {/* Milestone cards */}
      <div className="relative pl-6 space-y-4">
        {/* Vertical line */}
        <div className="absolute left-[11px] top-2 bottom-2 w-0.5 bg-slate-700" />

        {milestones.map((ms, i) => {
          const isDone = ms.status === 'completed'
          const isPast = new Date(ms.due_date) < now
          const msDate = new Date(ms.due_date)
          const daysLeft = Math.ceil((msDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))

          return (
            <div key={i} className="relative">
              {/* Dot */}
              <button
                onClick={() => onToggle(i, ms.status)}
                className={`absolute -left-6 top-1 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                  isDone ? 'bg-green-500/20 border-green-500' :
                  isPast ? 'bg-red-500/10 border-red-500' :
                  'bg-slate-800 border-slate-600 hover:border-amber-500'
                }`}
              >
                {isDone && <span className="text-[9px] text-green-400">✓</span>}
              </button>

              {/* Card */}
              <div className={`p-3 rounded-lg border transition-colors ${
                isDone ? 'bg-green-900/10 border-green-500/20' :
                isPast ? 'bg-red-900/10 border-red-500/20' :
                'bg-slate-800/50 border-slate-700/50 hover:border-slate-600'
              }`}>
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium ${isDone ? 'text-green-400 line-through' : 'text-slate-200'}`}>
                    {ms.title}
                  </span>
                  <span className={`text-xs ${
                    isDone ? 'text-green-500' : isPast ? 'text-red-400' : 'text-slate-500'
                  }`}>
                    {ms.due_date.slice(5)}
                    {!isDone && daysLeft >= 0 && ` (${daysLeft}일)`}
                    {!isDone && daysLeft < 0 && ` (${Math.abs(daysLeft)}일 초과)`}
                  </span>
                </div>
                {/* Gantt bar */}
                <div className="mt-2 relative h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                  <div className={`absolute inset-y-0 left-0 rounded-full ${
                    isDone ? 'bg-green-500' : isPast ? 'bg-red-500' : 'bg-amber-500/50'
                  }`} style={{ width: isDone ? '100%' : isPast ? '100%' : `${Math.max(100 - (daysLeft / totalDays * 100), 10)}%` }} />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
