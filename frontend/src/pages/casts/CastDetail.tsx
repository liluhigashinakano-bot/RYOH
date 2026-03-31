import { useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Camera, User, X, Trash2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

const RANKS = ['S', 'A', 'B+', 'B', 'C+', 'C', 'D', 'E']
const RANK_COLORS: Record<string, string> = {
  S: 'bg-yellow-900/40 text-yellow-300 border-yellow-700/40',
  A: 'bg-purple-900/40 text-purple-300 border-purple-700/40',
  'B+': 'bg-blue-900/40 text-blue-300 border-blue-700/40',
  B: 'bg-blue-900/30 text-blue-400 border-blue-700/30',
  'C+': 'bg-green-900/40 text-green-300 border-green-700/40',
  C: 'bg-night-700 text-gray-300 border-night-600',
  D: 'bg-night-700 text-gray-400 border-night-600',
  E: 'bg-night-700 text-gray-500 border-night-600',
}

const WEEKDAY_ORDER = ['月', '火', '水', '木', '金', '土', '日']

type Tab = 'info' | 'stats' | 'shifts'

function StatCard({ label, value, unit = '' }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="bg-night-800 border border-night-600 rounded-xl p-3 space-y-1">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-lg font-bold text-white">
        {value}
        {unit && <span className="text-xs text-gray-400 ml-1">{unit}</span>}
      </p>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex gap-3 py-2 border-b border-night-700">
      <span className="text-gray-500 text-sm w-36 flex-shrink-0">{label}</span>
      <span className="text-white text-sm">{value || '—'}</span>
    </div>
  )
}

export default function CastDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { stores, user } = useAuthStore()
  const qc = useQueryClient()
  const photoInputRef = useRef<HTMLInputElement>(null)
  const [tab, setTab] = useState<Tab>('info')
  const [showEdit, setShowEdit] = useState(false)

  const isManager = user && ['superadmin', 'manager', 'editor'].includes(user.role)

  // storeId はキャストの store_id から取得するため、まずどの店舗か検索
  const storeIds = stores.map(s => s.id)

  // 全店舗からキャストを探す（簡易実装：URLにstoreIdを含めないパターン）
  const { data: cast, isLoading } = useQuery({
    queryKey: ['cast-detail', id],
    queryFn: async () => {
      for (const sid of storeIds) {
        try {
          const r = await apiClient.get(`/api/casts/${sid}/${id}`)
          return { ...r.data, _storeId: sid }
        } catch { /* next */ }
      }
      throw new Error('キャストが見つかりません')
    },
    enabled: !!id && storeIds.length > 0,
  })

  const storeId = cast?._storeId

  const { data: stats } = useQuery({
    queryKey: ['cast-stats', storeId, id],
    queryFn: () => apiClient.get(`/api/casts/${storeId}/${id}/stats`).then(r => r.data),
    enabled: !!storeId && !!id,
  })

  const { data: shifts = [] } = useQuery({
    queryKey: ['cast-shifts', storeId, id],
    queryFn: () => apiClient.get(`/api/casts/${storeId}/${id}/shifts`).then(r => r.data),
    enabled: !!storeId && !!id && tab === 'shifts',
  })

  const uploadPhoto = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return apiClient.post(`/api/casts/${storeId}/${id}/photo`, fd)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cast-detail', id] }),
  })

  const updateCast = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiClient.put(`/api/casts/${storeId}/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cast-detail', id] })
      setShowEdit(false)
    },
  })

  const deleteCast = useMutation({
    mutationFn: () => apiClient.delete(`/api/casts/${storeId}/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['casts'] })
      navigate('/casts')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!cast) return <div className="text-gray-500 text-center py-20">キャストが見つかりません</div>

  const storeName = stores.find(s => s.id === storeId)?.name || ''

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      {/* ヘッダー */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/casts')} className="p-2 rounded-xl bg-night-800 hover:bg-night-700">
          <ArrowLeft className="w-5 h-5 text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white flex-1">{cast.stage_name}</h1>
        <span className={`badge border ${RANK_COLORS[cast.rank] || RANK_COLORS['C']}`}>{cast.rank}</span>
      </div>

      {/* プロフィール写真 */}
      <div className="card flex items-center gap-4">
        <div className="relative flex-shrink-0">
          <div className="w-20 h-20 rounded-full bg-night-700 border border-night-600 overflow-hidden flex items-center justify-center">
            {cast.photo_url
              ? <img src={cast.photo_url} alt={cast.stage_name} className="w-full h-full object-cover" />
              : <User className="w-10 h-10 text-gray-600" />
            }
          </div>
          <button
            onClick={() => photoInputRef.current?.click()}
            className="absolute bottom-0 right-0 w-6 h-6 bg-primary-600 rounded-full flex items-center justify-center hover:bg-primary-500"
          >
            <Camera className="w-3.5 h-3.5 text-white" />
          </button>
          <input
            ref={photoInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={e => {
              const f = e.target.files?.[0]
              if (f) uploadPhoto.mutate(f)
              e.target.value = ''
            }}
          />
        </div>
        <div>
          <p className="text-white font-bold text-lg">{cast.stage_name}</p>
          <p className="text-gray-400 text-sm">{storeName}</p>
          {cast.main_time_slot && <p className="text-gray-500 text-xs mt-1">{cast.main_time_slot}</p>}
        </div>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => setShowEdit(true)}
            className="btn-secondary text-sm px-3 py-1.5"
          >
            編集
          </button>
          {isManager && (
            <button
              onClick={() => {
                if (window.confirm(`${cast.stage_name} を削除しますか？`)) {
                  deleteCast.mutate()
                }
              }}
              className="p-1.5 rounded-xl bg-red-900/30 hover:bg-red-900/50 text-red-400 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* タブ */}
      <div className="flex gap-1 bg-night-800 rounded-xl p-1">
        {([['info', '基本情報'], ['stats', '統計'], ['shifts', '出勤履歴']] as [Tab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? 'bg-primary-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 基本情報タブ */}
      {tab === 'info' && (
        <div className="card space-y-0">
          <InfoRow label="基本時給" value={cast.hourly_rate ? `¥${cast.hourly_rate.toLocaleString()}` : null} />
          {stats && <InfoRow label="実質時給" value={`¥${stats.real_hourly_rate.toLocaleString()}`} />}
          <InfoRow label="ランク" value={cast.rank} />
          <InfoRow label="お酒" value={cast.alcohol_tolerance} />
          <InfoRow label="最寄駅" value={cast.nearest_station} />
          <InfoRow label="送迎" value={cast.transport_need ? '必要' : '不要'} />
          <InfoRow
            label="誕生日"
            value={cast.birthday ? new Date(cast.birthday).toLocaleDateString('ja-JP', { month: 'long', day: 'numeric' }) : null}
          />
          <InfoRow
            label="勤続開始日"
            value={cast.employment_start_date ? new Date(cast.employment_start_date).toLocaleDateString('ja-JP') : null}
          />
          <InfoRow
            label="最終時給変更日"
            value={cast.last_rate_change_date ? new Date(cast.last_rate_change_date).toLocaleDateString('ja-JP') : null}
          />
          {cast.notes && (
            <div className="py-2">
              <p className="text-gray-500 text-sm mb-1">備考</p>
              <p className="text-white text-sm whitespace-pre-wrap">{cast.notes}</p>
            </div>
          )}
        </div>
      )}

      {/* 統計タブ */}
      {tab === 'stats' && stats && (
        <div className="space-y-4">
          {/* 時給 */}
          <div>
            <p className="text-xs text-gray-500 mb-2">時給</p>
            <div className="grid grid-cols-3 gap-2">
              <StatCard label="基本時給" value={`¥${stats.hourly_rate.toLocaleString()}`} />
              <StatCard label="実質時給" value={`¥${stats.real_hourly_rate.toLocaleString()}`} />
              <StatCard label="ヘルプ時給" value={`¥${stats.help_hourly_rate.toLocaleString()}`} />
            </div>
          </div>

          {/* 出勤 */}
          <div>
            <p className="text-xs text-gray-500 mb-2">出勤</p>
            <div className="grid grid-cols-3 gap-2">
              <StatCard label="月間平均出勤" value={stats.avg_monthly_shifts} unit="回" />
              <StatCard label="月間総労働時間" value={stats.total_hours} unit="h" />
              <StatCard label="当欠率" value={stats.absent_rate} unit="%" />
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              <StatCard label="遅刻率" value={stats.late_rate} unit="%" />
              <StatCard label="日払い率" value={stats.daily_pay_ratio} unit="%" />
            </div>
          </div>

          {/* 曜日別平均労働時間 */}
          <div>
            <p className="text-xs text-gray-500 mb-2">曜日別平均労働時間</p>
            <div className="grid grid-cols-7 gap-1">
              {WEEKDAY_ORDER.map(wd => (
                <div key={wd} className="bg-night-800 border border-night-600 rounded-lg p-2 text-center">
                  <p className={`text-xs font-medium ${wd === '土' ? 'text-blue-400' : wd === '日' ? 'text-red-400' : 'text-gray-400'}`}>{wd}</p>
                  <p className="text-sm font-bold text-white mt-0.5">{stats.weekday_avg_hours[wd] ?? '—'}</p>
                  {stats.weekday_avg_hours[wd] && <p className="text-xs text-gray-600">h</p>}
                </div>
              ))}
            </div>
          </div>

          {/* 1セット(40分)あたり */}
          <div>
            <p className="text-xs text-gray-500 mb-2">1セット(40分)あたり</p>
            <div className="grid grid-cols-3 gap-2">
              <StatCard label="L数" value={stats.per_set_drinks} />
              <StatCard label="MG数" value={stats.per_set_mg} />
              <StatCard label="ショット数" value={stats.per_set_shots} />
              <StatCard label="シャンパンバック" value={`¥${Math.round(stats.per_set_champagne_back).toLocaleString()}`} />
              <StatCard label="Dバック" value={`¥${Math.round(stats.per_set_drink_back).toLocaleString()}`} />
            </div>
          </div>

          {/* 出勤1回あたり */}
          <div>
            <p className="text-xs text-gray-500 mb-2">出勤1回あたり</p>
            <div className="grid grid-cols-3 gap-2">
              <StatCard label="配布数" value={stats.per_shift_distribution} />
              <StatCard label="RT数" value={stats.per_shift_rt} />
              <StatCard label="NT数" value={stats.per_shift_nt} />
            </div>
          </div>
        </div>
      )}
      {tab === 'stats' && !stats && (
        <div className="text-center text-gray-500 py-12">統計データを読み込み中...</div>
      )}

      {/* 出勤履歴タブ */}
      {tab === 'shifts' && (
        <div className="space-y-2">
          {shifts.length === 0 && (
            <div className="text-center text-gray-500 py-12">出勤履歴がありません</div>
          )}
          {shifts.map((s: any) => (
            <div key={s.id} className="card flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-white font-medium text-sm">
                    {new Date(s.date).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric', weekday: 'short' })}
                  </span>
                  {s.is_absent && <span className="badge bg-red-900/40 text-red-400">当欠</span>}
                  {s.is_late && <span className="badge bg-yellow-900/40 text-yellow-400">遅刻</span>}
                </div>
                <p className="text-gray-500 text-xs mt-0.5">
                  {s.planned_start}〜{s.planned_end}
                  {s.actual_hours && ` / 実働 ${s.actual_hours}h`}
                </p>
              </div>
              {s.total_pay != null && (
                <div className="text-right flex-shrink-0">
                  <p className="text-white font-bold text-sm">¥{s.total_pay.toLocaleString()}</p>
                  {(s.drink_back || s.champagne_back) && (
                    <p className="text-gray-500 text-xs">
                      D¥{(s.drink_back || 0).toLocaleString()} C¥{(s.champagne_back || 0).toLocaleString()}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 編集モーダル */}
      {showEdit && (
        <EditCastModal
          cast={cast}
          isManager={!!isManager}
          onClose={() => setShowEdit(false)}
          onSave={(data) => updateCast.mutate(data)}
          isSaving={updateCast.isPending}
        />
      )}
    </div>
  )
}

function EditCastModal({
  cast,
  isManager,
  onClose,
  onSave,
  isSaving,
}: {
  cast: any
  isManager: boolean
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isSaving: boolean
}) {
  const [form, setForm] = useState({
    stage_name: cast.stage_name || '',
    rank: cast.rank || 'C',
    hourly_rate: cast.hourly_rate || 1400,
    help_hourly_rate: cast.help_hourly_rate || 1500,
    alcohol_tolerance: cast.alcohol_tolerance || '普通',
    main_time_slot: cast.main_time_slot || '',
    transport_need: cast.transport_need || false,
    nearest_station: cast.nearest_station || '',
    notes: cast.notes || '',
    birthday: cast.birthday || '',
    employment_start_date: cast.employment_start_date || '',
    last_rate_change_date: cast.last_rate_change_date || '',
  })

  const f = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(prev => ({ ...prev, [field]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-night-600 sticky top-0 bg-night-800">
          <h3 className="font-bold text-white">キャスト編集</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">源氏名 *</label>
            <input value={form.stage_name} onChange={f('stage_name')} className="input-field w-full" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-gray-400 block mb-1">ランク</label>
              <select value={form.rank} onChange={f('rank')} className="input-field w-full">
                {RANKS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-400 block mb-1">お酒</label>
              <select value={form.alcohol_tolerance} onChange={f('alcohol_tolerance')} className="input-field w-full">
                {['強', '普通', '弱'].map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
          </div>

          {/* 時給（管理者のみ） */}
          {isManager && (
            <div className="grid grid-cols-2 gap-3 p-3 bg-night-700 rounded-xl border border-night-600">
              <div>
                <label className="text-xs text-yellow-400 block mb-1">基本時給（管理者）</label>
                <input type="number" value={form.hourly_rate} onChange={f('hourly_rate')} className="input-field w-full" />
              </div>
              <div>
                <label className="text-xs text-yellow-400 block mb-1">ヘルプ時給</label>
                <input type="number" value={form.help_hourly_rate} onChange={f('help_hourly_rate')} className="input-field w-full" />
              </div>
            </div>
          )}

          <div>
            <label className="text-sm text-gray-400 block mb-1">主な出勤時間帯</label>
            <input value={form.main_time_slot} onChange={f('main_time_slot')} className="input-field w-full" placeholder="例: 20:00〜25:00" />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-400">送迎</label>
            <button
              type="button"
              onClick={() => setForm(prev => ({ ...prev, transport_need: !prev.transport_need }))}
              className={`px-3 py-1 rounded-lg text-sm ${form.transport_need ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400'}`}
            >
              {form.transport_need ? '必要' : '不要'}
            </button>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">最寄駅</label>
            <input value={form.nearest_station} onChange={f('nearest_station')} className="input-field w-full" />
          </div>
          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="text-sm text-gray-400 block mb-1">誕生日</label>
              <input type="date" value={form.birthday} onChange={f('birthday')} className="input-field w-full" />
            </div>
            <div>
              <label className="text-sm text-gray-400 block mb-1">勤続開始日</label>
              <input type="date" value={form.employment_start_date} onChange={f('employment_start_date')} className="input-field w-full" />
            </div>
            <div>
              <label className="text-sm text-gray-400 block mb-1">最終時給変更日</label>
              <input type="date" value={form.last_rate_change_date} onChange={f('last_rate_change_date')} className="input-field w-full" />
            </div>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">備考</label>
            <textarea value={form.notes} onChange={f('notes')} className="input-field w-full h-20 resize-none" />
          </div>
        </div>
        <div className="flex gap-3 p-4 border-t border-night-600">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => onSave(form)}
            disabled={!form.stage_name || isSaving}
            className="btn-primary flex-1"
          >
            {isSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
