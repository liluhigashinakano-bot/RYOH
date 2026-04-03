import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Trash2, Edit2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

type Tab = 'users' | 'stores' | 'casts'

export default function AdminPanel() {
  const [tab, setTab] = useState<Tab>('users')

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">管理者設定</h1>

      <div className="flex gap-2">
        {(['users', 'stores', 'casts'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
              tab === t ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400 hover:text-white'
            }`}
          >
            {t === 'users' ? 'ユーザー管理' : t === 'stores' ? '店舗管理' : 'キャスト管理'}
          </button>
        ))}
      </div>

      {tab === 'users' ? <UsersTab /> : tab === 'stores' ? <StoresTab /> : <CastsTab />}
    </div>
  )
}

function UsersTab() {
  const [showAdd, setShowAdd] = useState(false)
  const qc = useQueryClient()

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => apiClient.get('/api/users').then(r => r.data),
  })

  const { data: stores = [] } = useQuery({
    queryKey: ['stores'],
    queryFn: () => apiClient.get('/api/stores').then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  const ROLE_LABELS: Record<string, string> = {
    superadmin: 'スーパー管理者', manager: '管理者', editor: '編集者',
    staff: '従業員', order: 'オーダー端末', cast: 'キャスト', readonly: '閲覧のみ',
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-gray-400 text-sm">{users.length}件</p>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus className="w-4 h-4" />
          ユーザー追加
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-night-600 text-gray-400">
              <th className="text-left py-2 px-3">名前</th>
              <th className="text-left py-2 px-3">メール</th>
              <th className="text-left py-2 px-3">権限</th>
              <th className="text-left py-2 px-3">店舗</th>
              <th className="py-2 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u: any) => (
              <tr key={u.id} className="border-b border-night-700 hover:bg-night-700/50">
                <td className="py-2.5 px-3 font-medium text-white">{u.name}</td>
                <td className="py-2.5 px-3 text-gray-400">{u.email}</td>
                <td className="py-2.5 px-3">
                  <span className={`badge ${u.role === 'superadmin' ? 'bg-primary-900/50 text-primary-400' : 'bg-night-700 text-gray-300'}`}>
                    {ROLE_LABELS[u.role] || u.role}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-gray-400">
                  {stores.find((s: any) => s.id === u.store_id)?.name || '全店舗'}
                </td>
                <td className="py-2.5 px-3">
                  <button onClick={() => deleteMutation.mutate(u.id)} className="text-gray-600 hover:text-red-400 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && <AddUserModal stores={stores} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

function AddUserModal({ stores, onClose }: { stores: any[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ email: '', password: '', name: '', role: 'staff', store_id: '' })

  const mutation = useMutation({
    mutationFn: () => apiClient.post('/api/users', { ...form, store_id: form.store_id ? Number(form.store_id) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); onClose() },
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">ユーザー追加</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-3">
          <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" placeholder="名前" />
          <input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className="input-field w-full" placeholder="メールアドレス" type="email" />
          <input value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} className="input-field w-full" placeholder="パスワード" type="password" />
          <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className="input-field w-full">
            <option value="manager">管理者</option>
            <option value="editor">編集者</option>
            <option value="staff">従業員</option>
            <option value="order">オーダー端末</option>
            <option value="cast">キャスト</option>
            <option value="readonly">閲覧のみ</option>
          </select>
          <select value={form.store_id} onChange={e => setForm({ ...form, store_id: e.target.value })} className="input-field w-full">
            <option value="">全店舗</option>
            {stores.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.name || !form.email || !form.password} className="btn-primary flex-1">追加</button>
        </div>
      </div>
    </div>
  )
}

function StoresTab() {
  const [showAdd, setShowAdd] = useState(false)
  const qc = useQueryClient()
  const { stores: authStores, fetchMe } = useAuthStore()

  const { data: stores = [] } = useQuery({
    queryKey: ['stores-admin'],
    queryFn: () => apiClient.get('/api/stores').then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/stores/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stores-admin'] }); fetchMe() },
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-gray-400 text-sm">{stores.length}店舗</p>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus className="w-4 h-4" />
          店舗追加
        </button>
      </div>

      <div className="space-y-2">
        {stores.map((s: any) => (
          <div key={s.id} className="card flex items-center justify-between">
            <div>
              <p className="font-medium text-white">{s.name}</p>
              <p className="text-sm text-gray-400">セット ¥{s.set_price.toLocaleString()} / 延長 ¥{s.extension_price.toLocaleString()}</p>
            </div>
            <button onClick={() => deleteMutation.mutate(s.id)} className="text-gray-600 hover:text-red-400 transition-colors ml-4">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>

      {showAdd && <AddStoreModal onClose={() => setShowAdd(false)} />}
    </div>
  )
}

function CastsTab() {
  const { stores } = useAuthStore()
  const qc = useQueryClient()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)
  const [showAdd, setShowAdd] = useState(false)
  const [editCast, setEditCast] = useState<any | null>(null)

  const { data: casts = [] } = useQuery({
    queryKey: ['casts', selectedStoreId],
    queryFn: () => apiClient.get(`/api/casts/${selectedStoreId}`).then(r => r.data),
    enabled: !!selectedStoreId,
  })

  const deleteMutation = useMutation({
    mutationFn: (castId: number) => apiClient.delete(`/api/casts/${selectedStoreId}/${castId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['casts', selectedStoreId] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <select value={selectedStoreId} onChange={e => setSelectedStoreId(Number(e.target.value))} className="input-field text-sm">
          {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus className="w-4 h-4" />キャスト追加
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-night-600 text-gray-400">
              <th className="text-left py-2 px-3">ID</th>
              <th className="text-left py-2 px-3">名前</th>
              <th className="text-left py-2 px-3">在籍状況</th>
              <th className="py-2 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {casts.map((c: any) => (
              <tr key={c.id} className="border-b border-night-700 hover:bg-night-700/50">
                <td className="py-2.5 px-3 text-gray-500 text-xs">{c.cast_code || `#${c.id}`}</td>
                <td className="py-2.5 px-3 font-medium text-white">{c.name}</td>
                <td className="py-2.5 px-3">
                  <span className={`badge ${c.is_active ? 'bg-green-900/40 text-green-400' : 'bg-night-700 text-gray-500'}`}>
                    {c.is_active ? '在籍中' : '退職'}
                  </span>
                </td>
                <td className="py-2.5 px-3">
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setEditCast(c)} className="text-gray-500 hover:text-primary-400 transition-colors">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => { if (confirm(`${c.name}を削除しますか？`)) deleteMutation.mutate(c.id) }} className="text-gray-600 hover:text-red-400 transition-colors">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {casts.length === 0 && (
              <tr><td colSpan={4} className="text-center text-gray-600 py-8">キャストが登録されていません</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showAdd && <CastModal storeId={selectedStoreId} onClose={() => setShowAdd(false)} />}
      {editCast && <CastModal storeId={selectedStoreId} cast={editCast} onClose={() => setEditCast(null)} />}
    </div>
  )
}

function CastModal({ storeId, cast, onClose }: { storeId: number; cast?: any; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ stage_name: cast?.stage_name || cast?.name || '', is_active: cast?.is_active ?? true })

  const mutation = useMutation({
    mutationFn: () => cast
      ? apiClient.put(`/api/casts/${storeId}/${cast.id}`, form)
      : apiClient.post(`/api/casts/${storeId}`, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['casts', storeId] }); onClose() },
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">{cast ? 'キャスト編集' : 'キャスト追加'}</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-400 block mb-1.5">源氏名</label>
            <input value={form.stage_name} onChange={e => setForm({ ...form, stage_name: e.target.value })} className="input-field w-full" placeholder="源氏名" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1.5">在籍状況</label>
            <div className="flex gap-2">
              {[true, false].map(v => (
                <button key={String(v)} onClick={() => setForm({ ...form, is_active: v })}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${form.is_active === v ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                  {v ? '在籍中' : '退職'}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.stage_name} className="btn-primary flex-1 disabled:opacity-40">
            {cast ? '更新' : '追加'}
          </button>
        </div>
      </div>
    </div>
  )
}

function AddStoreModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const { fetchMe } = useAuthStore()
  const [form, setForm] = useState({ name: '', code: '', set_price: 0, extension_price: 2700 })

  const mutation = useMutation({
    mutationFn: () => apiClient.post('/api/stores', form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stores-admin'] }); fetchMe(); onClose() },
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">店舗追加</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-3">
          <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" placeholder="店舗名" />
          <input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} className="input-field w-full" placeholder="コード（英数字）例: nakameguro" />
          <input type="number" value={form.set_price} onChange={e => setForm({ ...form, set_price: Number(e.target.value) })} className="input-field w-full" placeholder="セット料金" />
          <input type="number" value={form.extension_price} onChange={e => setForm({ ...form, extension_price: Number(e.target.value) })} className="input-field w-full" placeholder="延長料金" />
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.name || !form.code} className="btn-primary flex-1">追加</button>
        </div>
      </div>
    </div>
  )
}
