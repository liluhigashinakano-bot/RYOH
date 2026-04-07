import { useState, useMemo } from 'react'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, X, User, Briefcase, Clock } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

type EmployeeTab = 'cast' | 'staff' | 'part_time'

const POSITIONS = ['シニアMG', 'エリアMG', 'マスタークルー', 'クルー①', 'クルー②', '準社員']

type SortKey =
  | '基本時給' | '実質時給' | '月間平均出勤' | '月間総労働時間'
  | '当欠率' | '遅刻率' | '日払い率'
  | 'L数' | 'MG数' | 'ショット数' | 'シャンパンバック' | 'Dバック'
  | '配布数' | 'RT数' | 'NT数'

const SORT_OPTIONS: SortKey[] = [
  '基本時給', '実質時給', '月間平均出勤', '月間総労働時間',
  '当欠率', '遅刻率', '日払い率',
  'L数', 'MG数', 'ショット数', 'シャンパンバック', 'Dバック',
  '配布数', 'RT数', 'NT数',
]

function getSortValue(cast: any, stats: any, key: SortKey): number {
  switch (key) {
    case '基本時給': return cast.hourly_rate ?? 0
    case '実質時給': return stats?.real_hourly_rate ?? 0
    case '月間平均出勤': return stats?.avg_monthly_shifts ?? 0
    case '月間総労働時間': return stats?.avg_monthly_hours ?? 0
    case '当欠率': return stats?.absent_rate ?? 0
    case '遅刻率': return stats?.late_rate ?? 0
    case '日払い率': return stats?.daily_pay_ratio ?? 0
    case 'L数': return stats?.per_set_drinks ?? 0
    case 'MG数': return stats?.per_set_mg ?? 0
    case 'ショット数': return stats?.per_set_shots ?? 0
    case 'シャンパンバック': return stats?.per_set_champagne_back ?? 0
    case 'Dバック': return stats?.per_set_drink_back ?? 0
    case '配布数': return stats?.per_shift_distribution ?? 0
    case 'RT数': return stats?.per_shift_rt ?? 0
    case 'NT数': return stats?.per_shift_nt ?? 0
  }
}

const RANKS = ['S', 'A', 'B+', 'B', 'C+', 'C', 'D', 'E']
const RANK_COLORS: Record<string, string> = {
  S: 'bg-yellow-900/40 text-yellow-300',
  A: 'bg-purple-900/40 text-purple-300',
  'B+': 'bg-blue-900/40 text-blue-300',
  B: 'bg-blue-900/30 text-blue-400',
  'C+': 'bg-green-900/40 text-green-300',
  C: 'bg-night-700 text-gray-300',
  D: 'bg-night-700 text-gray-400',
  E: 'bg-night-700 text-gray-500',
}

const WEEKDAY_ORDER = ['月', '火', '水', '木', '金', '土', '日']

function fmt(v: number | undefined | null, suffix = '') {
  if (v == null) return '—'
  return `${v}${suffix}`
}

function fmtYen(v: number | undefined | null) {
  if (v == null) return '—'
  return `¥${Math.round(v).toLocaleString()}`
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-0.5">
      <span className="text-gray-500 text-xs">{label}</span>
      <span className="text-gray-200 text-xs font-medium">{value}</span>
    </div>
  )
}

export default function CastList() {
  const { stores } = useAuthStore()
  const navigate = useNavigate()
  const [storeId, setStoreId] = useState(stores[0]?.id ?? 0)
  const [employeeTab, setEmployeeTab] = useState<EmployeeTab>('cast')
  const [showAdd, setShowAdd] = useState(false)
  const [showAddStaff, setShowAddStaff] = useState(false)
  const [editingStaff, setEditingStaff] = useState<any>(null)
  const [sortKey, setSortKey] = useState<SortKey>('月間総労働時間')
  const [sortAsc, setSortAsc] = useState(false)
  const qc = useQueryClient()

  const [retireTarget, setRetireTarget] = useState<any>(null)

  const { data: casts = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`, { params: { include_retired: true } }).then(r => r.data),
    enabled: !!storeId && employeeTab === 'cast',
  })

  const retireMutation = useMutation({
    mutationFn: (castId: number) => apiClient.post(`/api/casts/${storeId}/${castId}/retire`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['casts', storeId] })
      setRetireTarget(null)
    },
  })

  // 全キャストの統計を並列フェッチ
  const statsQueries = useQueries({
    queries: casts.map((cast: any) => ({
      queryKey: ['cast-stats', storeId, cast.id],
      queryFn: () => apiClient.get(`/api/casts/${storeId}/${cast.id}/stats`).then(r => r.data),
      enabled: !!storeId && employeeTab === 'cast',
      staleTime: 60000,
    })),
  })

  const statsMap: Record<number, any> = {}
  casts.forEach((cast: any, i: number) => {
    if (statsQueries[i]?.data) statsMap[cast.id] = statsQueries[i].data
  })

  const sortedCasts = useMemo(() => {
    const dir = sortAsc ? 1 : -1
    return [...casts].sort((a: any, b: any) => {
      // 退店は常に末尾
      if (a.is_retired !== b.is_retired) return a.is_retired ? 1 : -1
      const av = getSortValue(a, statsMap[a.id], sortKey)
      const bv = getSortValue(b, statsMap[b.id], sortKey)
      return (av - bv) * dir
    })
  }, [casts, statsMap, sortKey, sortAsc])

  // 社員・アルバイト一覧
  const { data: staffList = [] } = useQuery({
    queryKey: ['staff', employeeTab, storeId],
    queryFn: () => apiClient.get('/api/staff', { params: { employee_type: employeeTab, store_id: storeId } }).then(r => r.data),
    enabled: employeeTab === 'staff' || employeeTab === 'part_time',
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">従業員管理</h1>
        <div className="flex items-center gap-2">
          {employeeTab === 'cast' && (
            <>
              <select
                value={sortKey}
                onChange={e => setSortKey(e.target.value as SortKey)}
                className="input-field text-sm py-1.5"
              >
                {SORT_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              <button
                onClick={() => setSortAsc(v => !v)}
                className="btn-secondary px-2.5 py-1.5 text-sm"
              >
                {sortAsc ? '↑' : '↓'}
              </button>
              <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2">
                <Plus className="w-4 h-4" />キャスト追加
              </button>
            </>
          )}
          {(employeeTab === 'staff' || employeeTab === 'part_time') && (
            <button onClick={() => setShowAddStaff(true)} className="btn-primary flex items-center gap-2">
              <Plus className="w-4 h-4" />{employeeTab === 'staff' ? '社員追加' : 'アルバイト追加'}
            </button>
          )}
        </div>
      </div>

      {/* 従業員種別タブ */}
      <div className="flex gap-1 bg-night-800 rounded-xl p-1 w-fit">
        {([['cast', 'キャスト'], ['staff', '社員'], ['part_time', 'アルバイト']] as [EmployeeTab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => setEmployeeTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${employeeTab === t ? 'bg-primary-600 text-white' : 'text-gray-400 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* 店舗タブ（キャストのみ） */}
      {employeeTab === 'cast' && (
        <div className="flex gap-2 flex-wrap">
          {stores.map(s => (
            <button
              key={s.id}
              onClick={() => setStoreId(s.id)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
                storeId === s.id ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400 hover:text-white'
              }`}
            >
              {s.name}
              <span className="ml-2 text-xs opacity-60">
                {storeId === s.id ? `${casts.length}名` : ''}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* キャスト一覧 */}
      {employeeTab === 'cast' && <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {sortedCasts.map((cast: any) => {
          const stats = statsMap[cast.id]
          const birthday = cast.birthday
            ? new Date(cast.birthday).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' })
            : null
          const employmentStart = cast.employment_start_date
            ? new Date(cast.employment_start_date).toLocaleDateString('ja-JP', { year: 'numeric', month: 'numeric', day: 'numeric' })
            : null

          return (
            <div
              key={cast.id}
              className={`card text-left transition-colors space-y-3 relative ${cast.is_retired ? 'opacity-50 grayscale' : 'hover:border-primary-600/50 cursor-pointer'}`}
            >
              {/* 退店ボタン（右上） */}
              {!cast.is_retired && (
                <button
                  onClick={e => { e.stopPropagation(); setRetireTarget(cast) }}
                  className="absolute top-2 right-2 text-xs text-gray-600 hover:text-red-400 px-2 py-0.5 rounded hover:bg-red-900/20 transition-colors"
                >
                  退店
                </button>
              )}

              {/* クリックでキャスト詳細へ（退店以外） */}
              <div onClick={() => !cast.is_retired && navigate(`/casts/${cast.id}`)}>
              {/* ヘッダー */}
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full bg-night-700 border border-night-600 overflow-hidden flex items-center justify-center flex-shrink-0">
                  {cast.photo_url
                    ? <img src={cast.photo_url} alt={cast.stage_name} className="w-full h-full object-cover" />
                    : <User className="w-5 h-5 text-gray-600" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className={`font-bold truncate ${cast.is_retired ? 'text-gray-500' : 'text-white'}`}>{cast.stage_name}</h3>
                    {cast.is_retired
                      ? <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded-full">退店</span>
                      : <span className={`badge ${RANK_COLORS[cast.rank] || RANK_COLORS['C']} flex-shrink-0`}>{cast.rank}</span>
                    }
                  </div>
                  <div className="flex gap-3 text-xs text-gray-500 mt-0.5 flex-wrap">
                    {birthday && <span>誕生日 {birthday}</span>}
                    {cast.nearest_station && <span>{cast.nearest_station}</span>}
                  </div>
                  {employmentStart && (
                    <p className="text-xs text-gray-600 mt-0.5">勤続開始 {employmentStart}</p>
                  )}
                </div>
              </div>

              {/* 時給 */}
              <div className="flex gap-2">
                <div className="flex-1 bg-night-700 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">基本時給</p>
                  <p className="text-sm font-bold text-white">¥{cast.hourly_rate.toLocaleString()}</p>
                </div>
                <div className="flex-1 bg-night-700 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">実質時給</p>
                  <p className="text-sm font-bold text-primary-400">{stats ? `¥${stats.real_hourly_rate.toLocaleString()}` : '—'}</p>
                </div>
              </div>

              {/* 出勤統計 */}
              {stats && (
                <div className="space-y-0.5 border-t border-night-700 pt-2">
                  <StatRow label="月間平均出勤" value={fmt(stats.avg_monthly_shifts, '回')} />
                  <StatRow label="月間総労働時間" value={fmt(stats.avg_monthly_hours, 'h')} />
                  <StatRow label="当欠率" value={fmt(stats.absent_rate, '%')} />
                  <StatRow label="遅刻率" value={fmt(stats.late_rate, '%')} />
                  <StatRow label="日払い率" value={fmt(stats.daily_pay_ratio, '%')} />
                </div>
              )}

              {/* 曜日別 */}
              {stats?.weekday_avg_hours && Object.keys(stats.weekday_avg_hours).length > 0 && (
                <div className="border-t border-night-700 pt-2">
                  <p className="text-xs text-gray-500 mb-1">曜日別平均労働時間</p>
                  <div className="grid grid-cols-7 gap-0.5">
                    {WEEKDAY_ORDER.map(wd => (
                      <div key={wd} className="text-center">
                        <p className={`text-xs ${wd === '土' ? 'text-blue-400' : wd === '日' ? 'text-red-400' : 'text-gray-500'}`}>{wd}</p>
                        <p className="text-xs text-gray-300">{stats.weekday_avg_hours[wd] ?? '—'}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* セットあたり */}
              {stats && (
                <div className="border-t border-night-700 pt-2 space-y-0.5">
                  <p className="text-xs text-gray-500 mb-1">1セット(40分)あたり</p>
                  <StatRow label="L数" value={fmt(stats.per_set_drinks)} />
                  <StatRow label="MG数" value={fmt(stats.per_set_mg)} />
                  <StatRow label="ショット数" value={fmt(stats.per_set_shots)} />
                  <StatRow label="シャンパンバック" value={fmtYen(stats.per_set_champagne_back)} />
                  <StatRow label="Dバック" value={fmtYen(stats.per_set_drink_back)} />
                </div>
              )}

              {/* 出勤あたり */}
              {stats && (
                <div className="border-t border-night-700 pt-2 space-y-0.5">
                  <p className="text-xs text-gray-500 mb-1">出勤1回あたり</p>
                  <StatRow label="配布数" value={fmt(stats.per_shift_distribution)} />
                  <StatRow label="RT数" value={fmt(stats.per_shift_rt)} />
                  <StatRow label="NT数" value={fmt(stats.per_shift_nt)} />
                </div>
              )}
              </div>{/* クリックエリア終わり */}
            </div>
          )
        })}
        {casts.length === 0 && (
          <div className="col-span-full text-center text-gray-500 py-12">キャストがいません</div>
        )}
      </div>}

      {/* 社員・アルバイト一覧 */}
      {(employeeTab === 'staff' || employeeTab === 'part_time') && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(staffList as any[]).map((m: any) => (
            <button
              key={m.id}
              onClick={() => setEditingStaff(m)}
              className="card space-y-2 text-left hover:border-primary-600/50 transition-colors w-full"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-full bg-night-700 border border-night-600 flex items-center justify-center flex-shrink-0">
                    {employeeTab === 'staff' ? <Briefcase className="w-4 h-4 text-gray-500" /> : <Clock className="w-4 h-4 text-gray-500" />}
                  </div>
                  <div>
                    <p className="font-bold text-white text-sm">{m.name}</p>
                    {m.position && <p className="text-xs text-primary-400">{m.position}</p>}
                    {m.hourly_rate && <p className="text-xs text-gray-400">¥{m.hourly_rate.toLocaleString()}/h</p>}
                  </div>
                </div>
              </div>
              {m.store_ids?.length > 0 && (
                <div className="flex gap-1 flex-wrap">
                  {(m.store_ids as number[]).map((sid: number) => {
                    const s = stores.find(st => st.id === sid)
                    return s ? <span key={sid} className="badge text-xs bg-night-700 text-gray-400">{s.name}</span> : null
                  })}
                </div>
              )}
              {m.monthly_stats && (
                <div className="border-t border-night-700 pt-2 space-y-0.5">
                  <StatRow label="当月合計勤務時間" value={`${m.monthly_stats.monthly_hours}h`} />
                  <StatRow label="当月欠勤回数" value={`${m.monthly_stats.monthly_absent}回`} />
                  <StatRow label="当月遅刻回数" value={`${m.monthly_stats.monthly_late}回`} />
                </div>
              )}
            </button>
          ))}
          {(staffList as any[]).length === 0 && (
            <div className="col-span-full text-center text-gray-500 py-12">
              {employeeTab === 'staff' ? '社員がいません' : 'アルバイトがいません'}
            </div>
          )}
        </div>
      )}

      {/* 退店確認ポップアップ */}
      {retireTarget && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-night-800 border border-night-600 rounded-2xl w-full max-w-sm p-6 space-y-4">
            <p className="text-white font-bold text-center">退店確認</p>
            <p className="text-gray-300 text-sm text-center">
              <span className="text-white font-medium">{retireTarget.stage_name}</span> を退店にしますか？
            </p>
            <p className="text-gray-500 text-xs text-center">退店したキャストで間違いありませんか？</p>
            <div className="flex gap-3">
              <button onClick={() => setRetireTarget(null)} className="btn-secondary flex-1">キャンセル</button>
              <button
                onClick={() => retireMutation.mutate(retireTarget.id)}
                disabled={retireMutation.isPending}
                className="flex-1 bg-red-700 hover:bg-red-600 text-white py-2 rounded-lg text-sm font-medium transition-colors"
              >
                はい
              </button>
            </div>
          </div>
        </div>
      )}

      {showAdd && (
        <CastModal
          storeId={storeId}
          onClose={() => setShowAdd(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['casts', storeId] }); setShowAdd(false) }}
        />
      )}
      {showAddStaff && (
        <StaffModal
          employeeType={employeeTab as 'staff' | 'part_time'}
          stores={stores}
          onClose={() => setShowAddStaff(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['staff', employeeTab, storeId] }); setShowAddStaff(false) }}
        />
      )}
      {editingStaff && (
        <StaffEditModal
          staff={editingStaff}
          stores={stores}
          onClose={() => setEditingStaff(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['staff', employeeTab, storeId] }); setEditingStaff(null) }}
          onDeleted={() => { qc.invalidateQueries({ queryKey: ['staff', employeeTab, storeId] }); setEditingStaff(null) }}
        />
      )}
    </div>
  )
}

function CastModal({ storeId, onClose, onSaved }: { storeId: number; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    stage_name: '',
    rank: 'C',
    hourly_rate: 1400,
    alcohol_tolerance: '普通',
    main_time_slot: '',
    transport_need: false,
    nearest_station: '',
    notes: '',
  })

  const mutation = useMutation({
    mutationFn: () => apiClient.post(`/api/casts/${storeId}`, form),
    onSuccess: onSaved,
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-night-600 sticky top-0 bg-night-800">
          <h3 className="font-bold text-white">キャスト追加</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">源氏名 *</label>
            <input value={form.stage_name} onChange={e => setForm({ ...form, stage_name: e.target.value })} className="input-field w-full" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-gray-400 block mb-1">ランク</label>
              <select value={form.rank} onChange={e => setForm({ ...form, rank: e.target.value })} className="input-field w-full">
                {RANKS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-400 block mb-1">時給</label>
              <input type="number" value={form.hourly_rate} onChange={e => setForm({ ...form, hourly_rate: Number(e.target.value) })} step={50} className="input-field w-full" />
            </div>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">お酒</label>
            <select value={form.alcohol_tolerance} onChange={e => setForm({ ...form, alcohol_tolerance: e.target.value })} className="input-field w-full">
              {['強', '普通', '弱'].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">備考</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="input-field w-full h-20 resize-none" />
          </div>
        </div>
        <div className="flex gap-3 p-4 border-t border-night-600">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.stage_name} className="btn-primary flex-1">保存</button>
        </div>
      </div>
    </div>
  )
}

function StaffEditModal({ staff, stores, onClose, onSaved, onDeleted }: {
  staff: any
  stores: { id: number; name: string }[]
  onClose: () => void
  onSaved: () => void
  onDeleted: () => void
}) {
  const [form, setForm] = useState({
    name: staff.name ?? '',
    position: staff.position ?? POSITIONS[0],
    hourly_rate: staff.hourly_rate ?? 1200,
    store_ids: staff.store_ids ?? [] as number[],
    notes: staff.notes ?? '',
  })
  const [confirmDelete, setConfirmDelete] = useState(false)

  const updateMutation = useMutation({
    mutationFn: () => apiClient.put(`/api/staff/${staff.id}`, {
      name: form.name,
      position: staff.employee_type === 'staff' ? form.position : undefined,
      hourly_rate: staff.employee_type === 'part_time' ? form.hourly_rate : undefined,
      store_ids: form.store_ids,
      notes: form.notes,
    }),
    onSuccess: onSaved,
  })

  const deleteMutation = useMutation({
    mutationFn: () => apiClient.delete(`/api/staff/${staff.id}`),
    onSuccess: onDeleted,
  })

  const toggleStore = (id: number) => {
    setForm(prev => ({
      ...prev,
      store_ids: prev.store_ids.includes(id)
        ? prev.store_ids.filter((s: number) => s !== id)
        : [...prev.store_ids, id],
    }))
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-night-600 sticky top-0 bg-night-800">
          <h3 className="font-bold text-white">
            {staff.employee_type === 'staff' ? '社員' : 'アルバイト'}編集
          </h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">名前 *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" />
          </div>
          {staff.employee_type === 'staff' && (
            <div>
              <label className="text-sm text-gray-400 block mb-1">役職</label>
              <select value={form.position} onChange={e => setForm({ ...form, position: e.target.value })} className="input-field w-full">
                {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          )}
          {staff.employee_type === 'part_time' && (
            <div>
              <label className="text-sm text-gray-400 block mb-1">時給</label>
              <input type="number" value={form.hourly_rate} onChange={e => setForm({ ...form, hourly_rate: Number(e.target.value) })} step={50} className="input-field w-full" />
            </div>
          )}
          <div>
            <label className="text-sm text-gray-400 block mb-2">所属店舗</label>
            <div className="flex gap-2 flex-wrap">
              {stores.map(s => (
                <button key={s.id} type="button" onClick={() => toggleStore(s.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${form.store_ids.includes(s.id) ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400'}`}>
                  {s.name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">備考</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="input-field w-full h-20 resize-none" />
          </div>

          {/* 削除 */}
          {!confirmDelete ? (
            <button onClick={() => setConfirmDelete(true)} className="w-full text-red-400 text-sm py-2 border border-red-900/40 rounded-lg hover:bg-red-900/20 transition-colors">
              削除する
            </button>
          ) : (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-3 space-y-2">
              <p className="text-red-300 text-sm text-center">本当に削除しますか？</p>
              <div className="flex gap-2">
                <button onClick={() => setConfirmDelete(false)} className="btn-secondary flex-1 text-sm py-1.5">キャンセル</button>
                <button onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending} className="flex-1 bg-red-700 hover:bg-red-600 text-white text-sm py-1.5 rounded-lg transition-colors">
                  削除
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="flex gap-3 p-4 border-t border-night-600">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => updateMutation.mutate()} disabled={!form.name || updateMutation.isPending} className="btn-primary flex-1">保存</button>
        </div>
      </div>
    </div>
  )
}

function StaffModal({ employeeType, stores, onClose, onSaved }: {
  employeeType: 'staff' | 'part_time'
  stores: { id: number; name: string }[]
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState({
    name: '',
    position: POSITIONS[0],
    hourly_rate: 1200,
    store_ids: [] as number[],
    notes: '',
  })

  const mutation = useMutation({
    mutationFn: () => apiClient.post('/api/staff', {
      name: form.name,
      employee_type: employeeType,
      position: employeeType === 'staff' ? form.position : undefined,
      hourly_rate: employeeType === 'part_time' ? form.hourly_rate : undefined,
      store_ids: form.store_ids,
      notes: form.notes,
    }),
    onSuccess: onSaved,
  })

  const toggleStore = (id: number) => {
    setForm(prev => ({
      ...prev,
      store_ids: prev.store_ids.includes(id)
        ? prev.store_ids.filter(s => s !== id)
        : [...prev.store_ids, id],
    }))
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-night-600 sticky top-0 bg-night-800">
          <h3 className="font-bold text-white">{employeeType === 'staff' ? '社員追加' : 'アルバイト追加'}</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">名前 *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" />
          </div>
          {employeeType === 'staff' && (
            <div>
              <label className="text-sm text-gray-400 block mb-1">役職</label>
              <select value={form.position} onChange={e => setForm({ ...form, position: e.target.value })} className="input-field w-full">
                {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          )}
          {employeeType === 'part_time' && (
            <div>
              <label className="text-sm text-gray-400 block mb-1">時給</label>
              <input type="number" value={form.hourly_rate} onChange={e => setForm({ ...form, hourly_rate: Number(e.target.value) })} step={50} className="input-field w-full" />
            </div>
          )}
          <div>
            <label className="text-sm text-gray-400 block mb-2">所属店舗</label>
            <div className="flex gap-2 flex-wrap">
              {stores.map(s => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => toggleStore(s.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${form.store_ids.includes(s.id) ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400'}`}
                >
                  {s.name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">備考</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="input-field w-full h-20 resize-none" />
          </div>
        </div>
        <div className="flex gap-3 p-4 border-t border-night-600">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.name} className="btn-primary flex-1">保存</button>
        </div>
      </div>
    </div>
  )
}
