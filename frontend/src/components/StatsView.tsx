import { useState, useEffect } from 'react'
import type { Schedule } from '../types'
import { CATEGORIES } from '../types'
import { api } from '../lib/api'

export function StatsView() {
  const [weekSchedules, setWeekSchedules] = useState<Schedule[]>([])
  const [upcoming, setUpcoming] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const now = new Date()
        // This week (Mon-Sun)
        const dow = now.getDay()
        const monday = new Date(now)
        monday.setDate(now.getDate() - ((dow + 6) % 7))
        const sunday = new Date(monday)
        sunday.setDate(monday.getDate() + 6)

        const fromDate = `${monday.toISOString().slice(0, 10)}T00:00:00`
        const toDate = `${sunday.toISOString().slice(0, 10)}T23:59:59`

        const [week, up] = await Promise.all([
          api.list({ from_date: fromDate, to_date: toDate }),
          api.upcoming(72), // next 3 days
        ])
        setWeekSchedules(week)
        setUpcoming(up)
      } catch {
        // ignore
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <svg className="animate-spin h-8 w-8 text-blue-500" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    )
  }

  // Category distribution
  const catCounts: Record<string, number> = {}
  for (const s of weekSchedules) {
    catCounts[s.category] = (catCounts[s.category] || 0) + 1
  }

  // Daily distribution
  const dayNames = ['월', '화', '수', '목', '금', '토', '일']
  const dailyCounts = new Array(7).fill(0)
  for (const s of weekSchedules) {
    const d = new Date(s.start_at).getDay()
    const idx = (d + 6) % 7 // Mon=0
    dailyCounts[idx]++
  }
  const maxDaily = Math.max(...dailyCounts, 1)

  const total = weekSchedules.length
  const completed = weekSchedules.filter(s => s.status === 'completed').length

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="이번 주 일정" value={`${total}건`} color="blue" />
        <StatCard label="완료" value={`${completed}건`} color="green" />
        <StatCard label="진행 중" value={`${total - completed}건`} color="amber" />
        <StatCard label="다가오는 일정" value={`${upcoming.length}건`} sub="72시간 내" color="purple" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category pie chart */}
        <div className="bg-slate-800/80 rounded-xl border border-slate-700/50 p-5">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">카테고리별 분포</h3>
          {total > 0 ? (
            <div className="flex items-center gap-6">
              <PieChart data={catCounts} total={total} />
              <div className="space-y-2">
                {Object.entries(CATEGORIES).map(([key, val]) => {
                  const count = catCounts[key] || 0
                  if (count === 0) return null
                  const pct = Math.round(count / total * 100)
                  return (
                    <div key={key} className="flex items-center gap-2">
                      <span className={`w-3 h-3 rounded-sm ${val.bg}`} />
                      <span className={`text-sm ${val.color}`}>{val.label}</span>
                      <span className="text-xs text-slate-500">{count}건 ({pct}%)</span>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <p className="text-slate-500 text-sm">이번 주 일정이 없습니다</p>
          )}
        </div>

        {/* Daily distribution bar chart */}
        <div className="bg-slate-800/80 rounded-xl border border-slate-700/50 p-5">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">요일별 분포</h3>
          <div className="flex items-end gap-3 h-32">
            {dayNames.map((name, i) => {
              const count = dailyCounts[i]
              const h = (count / maxDaily) * 100
              const isToday = i === (new Date().getDay() + 6) % 7
              return (
                <div key={name} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-xs text-slate-400">{count}</span>
                  <div className={`w-full rounded-t transition-all ${
                    isToday ? 'bg-blue-500' : 'bg-slate-600'
                  }`} style={{ height: `${Math.max(h, 4)}%` }} />
                  <span className={`text-xs ${isToday ? 'text-blue-400 font-bold' : 'text-slate-500'}`}>{name}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Upcoming reminders */}
      <div className="bg-slate-800/80 rounded-xl border border-slate-700/50 p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">다가오는 일정 (72시간)</h3>
        {upcoming.length > 0 ? (
          <div className="space-y-2">
            {upcoming.map((s, i) => {
              const cat = CATEGORIES[s.category] || CATEGORIES.general
              const dt = new Date(s.start_at)
              const now = new Date()
              const hoursLeft = Math.round((dt.getTime() - now.getTime()) / (1000 * 60 * 60))
              const timeStr = dt.toLocaleString('ko-KR', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
              })

              return (
                <div key={`${s.id}-${i}`} className="flex items-center gap-3 py-2 px-3 hover:bg-slate-700/30 rounded-lg">
                  <div className={`w-1 h-8 rounded-full ${
                    cat.color.includes('blue') ? 'bg-blue-500' :
                    cat.color.includes('orange') ? 'bg-orange-500' :
                    cat.color.includes('green') ? 'bg-green-500' :
                    'bg-purple-500'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-200 truncate">{s.title}</div>
                    <div className="text-xs text-slate-500">{timeStr}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    hoursLeft <= 1 ? 'bg-red-500/20 text-red-400' :
                    hoursLeft <= 12 ? 'bg-amber-500/20 text-amber-400' :
                    'bg-slate-700 text-slate-400'
                  }`}>
                    {hoursLeft <= 0 ? '진행 중' : hoursLeft < 1 ? '곧' : `${hoursLeft}시간 후`}
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-slate-500 text-sm">72시간 내 일정이 없습니다</p>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color: string }) {
  const colorMap: Record<string, string> = {
    blue: 'from-blue-500/10 to-blue-500/5 border-blue-500/20',
    green: 'from-green-500/10 to-green-500/5 border-green-500/20',
    amber: 'from-amber-500/10 to-amber-500/5 border-amber-500/20',
    purple: 'from-purple-500/10 to-purple-500/5 border-purple-500/20',
  }
  const textMap: Record<string, string> = {
    blue: 'text-blue-400',
    green: 'text-green-400',
    amber: 'text-amber-400',
    purple: 'text-purple-400',
  }

  return (
    <div className={`bg-gradient-to-br ${colorMap[color]} border rounded-xl p-4`}>
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${textMap[color]}`}>{value}</div>
      {sub && <div className="text-[10px] text-slate-600 mt-0.5">{sub}</div>}
    </div>
  )
}

/** Simple SVG donut chart */
function PieChart({ data, total }: { data: Record<string, number>; total: number }) {
  const size = 120
  const radius = 45
  const strokeWidth = 20
  const cx = size / 2
  const cy = size / 2

  const colorMap: Record<string, string> = {
    general: '#3b82f6',
    work: '#f97316',
    personal: '#22c55e',
    meeting: '#a855f7',
  }

  let offset = 0
  const segments = Object.entries(data).filter(([, count]) => count > 0).map(([key, count]) => {
    const pct = count / total
    const dasharray = 2 * Math.PI * radius * pct
    const dashoffset = 2 * Math.PI * radius * (1 - pct)
    const rotation = offset * 360 - 90
    offset += pct
    return { key, dasharray, dashoffset, rotation, color: colorMap[key] || '#64748b' }
  })

  const circumference = 2 * Math.PI * radius

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* Background ring */}
      <circle cx={cx} cy={cy} r={radius} fill="none" stroke="#1e293b" strokeWidth={strokeWidth} />

      {segments.map((seg) => (
        <circle
          key={seg.key}
          cx={cx} cy={cy} r={radius}
          fill="none"
          stroke={seg.color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${seg.dasharray} ${circumference - seg.dasharray}`}
          transform={`rotate(${seg.rotation} ${cx} ${cy})`}
          strokeLinecap="round"
        />
      ))}

      {/* Center text */}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize="18" fontWeight="bold" fill="#e2e8f0">
        {total}
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize="9" fill="#64748b">
        이번 주
      </text>
    </svg>
  )
}
