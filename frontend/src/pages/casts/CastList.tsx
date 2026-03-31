import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, X, User } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

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

export default function CastList() {
  const { stores } = useAuthStore()
  const navigate = useNavigate()
  const [storeId, setStoreId] = useState(stores[0]?.id ?? 0)
  const [showAdd, setShowAdd] = useState(false)
  const qc = useQueryClient()

  const { data: casts = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
    enabled: !!storeId,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">キャスト管理</h1>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          キャスト追加
        </button>
      </div>

      {/* 店舗タブ */}
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

      {/* キャスト一覧 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {casts.map((cast: any) => (
          <button
            key={cast.id}
            onClick={() => navigate(`/casts/${cast.id}`)}
            className="card text-left space-y-3 hover:border-primary-600/50 transition-colors"
          >
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-night-700 border border-night-600 overflow-hidden flex items-center justify-center flex-shrink-0">
                {cast.photo_url
                  ? <img src={cast.photo_url} alt={cast.stage_name} className="w-full h-full object-cover" />
                  : <User className="w-5 h-5 text-gray-600" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-start">
                  <h3 className="font-bold text-white truncate">{cast.stage_name}</h3>
                  <span className={`badge ${RANK_COLORS[cast.rank] || RANK_COLORS['C']} ml-2 flex-shrink-0`}>{cast.rank}</span>
                </div>
                <div className="text-sm space-y-0.5 text-gray-400 mt-1">
                  <p>時給 ¥{cast.hourly_rate.toLocaleString()}</p>
                  {cast.main_time_slot && <p>{cast.main_time_slot}</p>}
                  {cast.alcohol_tolerance && <p>お酒: {cast.alcohol_tolerance}</p>}
                </div>
              </div>
            </div>
          </button>
        ))}
        {casts.length === 0 && (
          <div className="col-span-full text-center text-gray-500 py-12">キャストがいません</div>
        )}
      </div>

      {showAdd && (
        <CastModal
          storeId={storeId}
          onClose={() => setShowAdd(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['casts', storeId] }); setShowAdd(false) }}
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
              <input type="number" value={form.hourly_rate} onChange={e => setForm({ ...form, hourly_rate: Number(e.target.value) })} className="input-field w-full" />
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
