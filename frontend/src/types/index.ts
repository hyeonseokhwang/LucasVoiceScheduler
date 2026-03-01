export interface Recurrence {
  freq: 'daily' | 'weekly' | 'monthly' | 'yearly'
  interval: number
  days?: number[] // 0=Mon ... 6=Sun
  until?: string
}

export interface Schedule {
  id: number
  title: string
  description?: string | null
  start_at: string
  end_at?: string | null
  all_day: boolean | number
  category: string
  remind_at?: string | null
  status: 'active' | 'completed' | 'cancelled'
  created_at: string
  recurrence?: string | null
  parent_id?: number | null
  _is_occurrence?: boolean
  _occurrence_date?: string
}

export interface ScheduleFormData {
  title: string
  description?: string
  start_at: string
  end_at?: string
  all_day: boolean
  category: string
  remind_at?: string
  recurrence?: Recurrence | null
  parent_id?: number
}

export interface Milestone {
  title: string
  due_date: string
  status: 'pending' | 'completed'
}

export interface Earning {
  id: number
  challenge_id: number
  amount: number
  source?: string | null
  date: string
  note?: string | null
  created_at: string
}

export interface ChallengeProgress {
  percentage: number
  d_day: number | null
  milestones_total: number
  milestones_done: number
  remaining: number
}

export interface Challenge {
  id: number
  title: string
  description?: string | null
  target_amount: number
  current_amount: number
  deadline: string
  status: 'active' | 'completed' | 'failed' | 'cancelled'
  milestones?: Milestone[] | null
  earnings?: Earning[]
  progress?: ChallengeProgress
  created_at: string
}

export type ViewMode = 'month' | 'week' | 'day'

export const CATEGORIES: Record<string, { label: string; color: string; bg: string }> = {
  general: { label: '일반', color: 'text-blue-400', bg: 'bg-blue-500/20 border-blue-500/30' },
  work: { label: '업무', color: 'text-orange-400', bg: 'bg-orange-500/20 border-orange-500/30' },
  personal: { label: '개인', color: 'text-green-400', bg: 'bg-green-500/20 border-green-500/30' },
  meeting: { label: '회의', color: 'text-purple-400', bg: 'bg-purple-500/20 border-purple-500/30' },
}
