import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Trash2, Edit2, Shield, ChevronDown, ChevronUp } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

type Tab = 'users' | 'account-perms' | 'group-perms' | 'stores'

const PERM_PAGES = [
  { key: 'realtime', label: 'リアルタイム状況', hasEdit: false },
  { key: 'pos', label: 'POS・伝票', hasEdit: true },
  { key: 'customers', label: '顧客管理', hasEdit: true },
  { key: 'employees', label: '従業員管理', hasEdit: true },
  { key: 'accounts', label: 'アカウント管理', hasEdit: true },
  { key: 'menus', label: 'メニュー管理', hasEdit: true },
]

const ROLE_LABELS: Record<string, string> = {
  administrator: 'administrator', superadmin: 'administrator',
  manager: '管理者', editor: '編集者', staff: '従業員',
  order: 'オーダー端末', cast: 'キャスト', readonly: '閲覧のみ',
}

const ROLE_OPTIONS = [
  { value: 'manager', label: '管理者' },
  { value: 'editor', label: '編集者' },
  { value: 'staff', label: '従業員' },
  { value: 'order', label: 'オーダー端末' },
  { value: 'cast', label: 'キャスト' },
  { value: 'readonly', label: '閲覧のみ' },
]

export default function AdminPanel() {
  const { isAdministrator, hasPermission } = useAuthStore()
  const [tab, setTab] = useState<Tab>('users')

  const canEdit = hasPermission('accounts', 'edit')

  const tabs = [
    { key: 'users', label: 'ユーザー管理' },
    { key: 'account-perms', label: '権限管理（アカウント別）' },
    { key: 'group-perms', label: '権限管理（グループ別）' },
    { key: 'stores', label: '店舗管理' },
  ] as const

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">アカウント管理</h1>

      <div className="flex gap-2 flex-wrap">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'users' && <UsersTab canEdit={canEdit} />}
      {tab === 'account-perms' && <AccountPermsTab canEdit={canEdit} />}
      {tab === 'group-perms' && <GroupPermsTab canEdit={isAdministrator()} />}
      {tab === 'stores' && <StoresTab />}
    </div>
  )
}

// ─── ユーザー管理 ────────────────────────────
function UsersTab({ canEdit }: { canEdit: boolean }) {
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
    onError: (e: any) => alert(e?.response?.data?.detail ?? '削除に失敗しました'),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-gray-400 text-sm">{users.length}件</p>
        {canEdit && (
          <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
            <Plus className="w-4 h-4" />ユーザー追加
          </button>
        )}
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-night-600 text-gray-400">
              <th className="text-left py-2 px-3">名前</th>
              <th className="text-left py-2 px-3">メール</th>
              <th className="text-left py-2 px-3">権限ロール</th>
              <th className="text-left py-2 px-3">店舗</th>
              {canEdit && <th className="py-2 px-3"></th>}
            </tr>
          </thead>
          <tbody>
            {(users as any[]).map((u: any) => (
              <tr key={u.id} className="border-b border-night-700 hover:bg-night-700/50">
                <td className="py-2.5 px-3 font-medium text-white">{u.name}</td>
                <td className="py-2.5 px-3 text-gray-400">{u.email}</td>
                <td className="py-2.5 px-3">
                  <span className={`badge ${['administrator','superadmin'].includes(u.role) ? 'bg-primary-900/50 text-primary-400' : 'bg-night-700 text-gray-300'}`}>
                    {ROLE_LABELS[u.role] ?? u.role}
                  </span>
                  {u.permissions !== null && u.permissions !== undefined && (
                    <span className="ml-1 text-xs text-yellow-500">カスタム</span>
                  )}
                </td>
                <td className="py-2.5 px-3 text-gray-400">
                  {(stores as any[]).find((s: any) => s.id === u.store_id)?.name || '全店舗'}
                </td>
                {canEdit && (
                  <td className="py-2.5 px-3">
                    {!['administrator','superadmin'].includes(u.role) && (
                      <button onClick={() => { if (confirm(`${u.name}を削除しますか？`)) deleteMutation.mutate(u.id) }}
                        className="text-gray-600 hover:text-red-400 transition-colors">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && <AddUserModal stores={stores as any[]} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

// ─── アカウント別権限管理 ───────────────────────
function AccountPermsTab({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editPerms, setEditPerms] = useState<Record<string, any>>({})

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => apiClient.get('/api/users').then(r => r.data),
  })
  const { data: rolePerms = {} } = useQuery({
    queryKey: ['role-permissions'],
    queryFn: () => apiClient.get('/api/users/role-permissions').then(r => r.data),
  })

  const updatePermsMutation = useMutation({
    mutationFn: ({ userId, permissions }: { userId: number; permissions: any }) =>
      apiClient.post(`/api/users/${userId}/permissions`, { permissions }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setExpandedId(null)
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? '更新に失敗しました'),
  })

  const nonAdminUsers = (users as any[]).filter((u: any) => !['administrator','superadmin'].includes(u.role))

  const startEdit = (u: any) => {
    const base = u.permissions ?? (rolePerms as any)[u.role] ?? {}
    // deep copy
    const copy: any = {}
    for (const p of PERM_PAGES) {
      copy[p.key] = { view: !!(base[p.key]?.view), edit: !!(base[p.key]?.edit) }
    }
    setEditPerms(copy)
    setExpandedId(u.id)
  }

  const togglePerm = (page: string, type: string) => {
    setEditPerms(prev => ({
      ...prev,
      [page]: { ...prev[page], [type]: !prev[page]?.[type] },
    }))
  }

  return (
    <div className="space-y-3">
      <p className="text-gray-400 text-sm">各アカウントの閲覧・編集権限を個別に設定します。設定しない場合はグループ（ロール）のデフォルト権限が適用されます。</p>
      {nonAdminUsers.map((u: any) => (
        <div key={u.id} className="card space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-white font-medium">{u.name}</span>
              <span className="text-xs text-gray-500 ml-2">{u.email}</span>
              <span className="text-xs text-gray-400 ml-2 bg-night-700 px-1.5 py-0.5 rounded">{ROLE_LABELS[u.role] ?? u.role}</span>
              {u.permissions !== null && u.permissions !== undefined && (
                <span className="text-xs text-yellow-500 ml-2">● カスタム権限</span>
              )}
            </div>
            {canEdit && (
              <div className="flex gap-2">
                {u.permissions !== null && u.permissions !== undefined && (
                  <button onClick={() => updatePermsMutation.mutate({ userId: u.id, permissions: null })}
                    className="text-xs text-gray-500 hover:text-red-400 transition-colors">
                    リセット
                  </button>
                )}
                <button onClick={() => expandedId === u.id ? setExpandedId(null) : startEdit(u)}
                  className="text-xs flex items-center gap-1 text-primary-400 hover:text-primary-300 transition-colors">
                  <Shield className="w-3.5 h-3.5" />
                  権限編集
                  {expandedId === u.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
              </div>
            )}
          </div>

          {expandedId === u.id && (
            <div className="border-t border-night-600 pt-3 space-y-2">
              <PermMatrix perms={editPerms} onChange={togglePerm} editable={true} />
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={() => setExpandedId(null)} className="btn-secondary text-sm px-3 py-1.5">キャンセル</button>
                <button
                  onClick={() => updatePermsMutation.mutate({ userId: u.id, permissions: editPerms })}
                  disabled={updatePermsMutation.isPending}
                  className="btn-primary text-sm px-3 py-1.5">
                  保存
                </button>
              </div>
            </div>
          )}

          {expandedId !== u.id && (
            <PermMatrix perms={u.permissions ?? (rolePerms as any)[u.role] ?? {}} editable={false} />
          )}
        </div>
      ))}
    </div>
  )
}

// ─── グループ別権限管理 ─────────────────────────
function GroupPermsTab({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const [editingRole, setEditingRole] = useState<string | null>(null)
  const [editPerms, setEditPerms] = useState<Record<string, any>>({})

  const { data: rolePerms = {} } = useQuery({
    queryKey: ['role-permissions'],
    queryFn: () => apiClient.get('/api/users/role-permissions').then(r => r.data),
  })

  const updateMutation = useMutation({
    mutationFn: ({ role, permissions }: { role: string; permissions: any }) =>
      apiClient.post(`/api/users/role-permissions/${role}`, { permissions }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['role-permissions'] })
      setEditingRole(null)
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? '更新に失敗しました'),
  })

  const startEdit = (role: string) => {
    const base = (rolePerms as any)[role] ?? {}
    const copy: any = {}
    for (const p of PERM_PAGES) {
      copy[p.key] = { view: !!(base[p.key]?.view), edit: !!(base[p.key]?.edit) }
    }
    setEditPerms(copy)
    setEditingRole(role)
  }

  const togglePerm = (page: string, type: string) => {
    setEditPerms(prev => ({
      ...prev,
      [page]: { ...prev[page], [type]: !prev[page]?.[type] },
    }))
  }

  return (
    <div className="space-y-4">
      <p className="text-gray-400 text-sm">ロール（グループ）ごとのデフォルト権限を設定します。アカウント別でカスタム権限が設定されている場合、そちらが優先されます。</p>
      {ROLE_OPTIONS.map(({ value: role, label }) => (
        <div key={role} className="card space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-medium text-white">{label}</span>
            {canEdit && (
              <button onClick={() => editingRole === role ? setEditingRole(null) : startEdit(role)}
                className="text-xs flex items-center gap-1 text-primary-400 hover:text-primary-300 transition-colors">
                <Shield className="w-3.5 h-3.5" />
                権限編集
                {editingRole === role ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            )}
          </div>

          {editingRole === role ? (
            <div className="border-t border-night-600 pt-3 space-y-2">
              <PermMatrix perms={editPerms} onChange={togglePerm} editable={true} />
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={() => setEditingRole(null)} className="btn-secondary text-sm px-3 py-1.5">キャンセル</button>
                <button
                  onClick={() => updateMutation.mutate({ role, permissions: editPerms })}
                  disabled={updateMutation.isPending}
                  className="btn-primary text-sm px-3 py-1.5">
                  保存
                </button>
              </div>
            </div>
          ) : (
            <PermMatrix perms={(rolePerms as any)[role] ?? {}} editable={false} />
          )}
        </div>
      ))}
    </div>
  )
}

// ─── 権限マトリクス共通コンポーネント ─────────────
function PermMatrix({ perms, editable, onChange }: {
  perms: Record<string, any>
  editable: boolean
  onChange?: (page: string, type: string) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500">
            <th className="text-left py-1 pr-4 font-normal">ページ</th>
            <th className="text-center py-1 px-3 font-normal w-16">閲覧</th>
            <th className="text-center py-1 px-3 font-normal w-16">編集</th>
          </tr>
        </thead>
        <tbody>
          {PERM_PAGES.map(({ key, label, hasEdit }) => (
            <tr key={key} className="border-t border-night-700/50">
              <td className="py-1.5 pr-4 text-gray-300">{label}</td>
              <td className="text-center py-1.5 px-3">
                <PermCell
                  value={!!(perms[key]?.view)}
                  editable={editable}
                  onChange={editable ? () => onChange?.(key, 'view') : undefined}
                />
              </td>
              <td className="text-center py-1.5 px-3">
                {hasEdit ? (
                  <PermCell
                    value={!!(perms[key]?.edit)}
                    editable={editable}
                    onChange={editable ? () => onChange?.(key, 'edit') : undefined}
                  />
                ) : <span className="text-gray-700">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PermCell({ value, editable, onChange }: { value: boolean; editable: boolean; onChange?: () => void }) {
  if (editable) {
    return (
      <button onClick={onChange}
        className={`w-6 h-6 rounded flex items-center justify-center mx-auto transition-colors ${value ? 'bg-green-700 text-white' : 'bg-night-700 text-gray-600 hover:bg-night-600'}`}>
        {value ? '✓' : '×'}
      </button>
    )
  }
  return (
    <span className={`text-sm ${value ? 'text-green-400' : 'text-gray-700'}`}>
      {value ? '✓' : '×'}
    </span>
  )
}

// ─── ユーザー追加モーダル ────────────────────────
function AddUserModal({ stores, onClose }: { stores: any[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ email: '', password: '', name: '', role: 'staff', store_id: '' })

  const mutation = useMutation({
    mutationFn: () => apiClient.post('/api/users', { ...form, store_id: form.store_id ? Number(form.store_id) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); onClose() },
    onError: (e: any) => alert(e?.response?.data?.detail ?? '追加に失敗しました'),
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
            {ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
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

// ─── 店舗管理 ────────────────────────────────
function StoresTab() {
  const [showAdd, setShowAdd] = useState(false)
  const [editStore, setEditStore] = useState<any | null>(null)
  const qc = useQueryClient()
  const { fetchMe, isAdministrator } = useAuthStore()
  const canEdit = isAdministrator()

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
        <p className="text-gray-400 text-sm">{(stores as any[]).length}店舗</p>
        {canEdit && (
          <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
            <Plus className="w-4 h-4" />店舗追加
          </button>
        )}
      </div>

      <div className="space-y-2">
        {(stores as any[]).map((s: any) => (
          <div key={s.id} className="card flex items-center justify-between">
            <div>
              <p className="font-medium text-white">{s.name}</p>
              <p className="text-sm text-gray-400">
                営業時間 {s.open_time || '—'}～{s.close_time || '—'}
              </p>
            </div>
            {canEdit && (
              <div className="flex items-center gap-2 ml-4">
                <button onClick={() => setEditStore(s)} className="text-gray-500 hover:text-primary-400 transition-colors">
                  <Edit2 className="w-4 h-4" />
                </button>
                <button onClick={() => deleteMutation.mutate(s.id)} className="text-gray-600 hover:text-red-400 transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {showAdd && <AddStoreModal onClose={() => setShowAdd(false)} />}
      {editStore && <EditStoreModal store={editStore} onClose={() => setEditStore(null)} />}
    </div>
  )
}

function TimeSelect({ value, onChange, minHour = 0 }: { value: string; onChange: (v: string) => void; minHour?: number }) {
  const [h, m] = value ? value.split(':').map(Number) : [minHour, 0]
  const setH = (newH: number) => onChange(`${String(newH).padStart(2,'0')}:${String(m).padStart(2,'0')}`)
  const setM = (newM: number) => onChange(`${String(h).padStart(2,'0')}:${String(newM).padStart(2,'0')}`)
  return (
    <div className="flex items-center gap-1">
      <select value={h} onChange={e => setH(Number(e.target.value))} className="input-field text-sm w-20">
        {Array.from({ length: 36 - minHour }, (_, i) => i + minHour).map(n => (
          <option key={n} value={n}>{String(n).padStart(2,'0')}</option>
        ))}
      </select>
      <span className="text-gray-400">:</span>
      <select value={m} onChange={e => setM(Number(e.target.value))} className="input-field text-sm w-20">
        {[0, 15, 30, 45].map(n => <option key={n} value={n}>{String(n).padStart(2,'0')}</option>)}
      </select>
    </div>
  )
}

function EditStoreModal({ store, onClose }: { store: any; onClose: () => void }) {
  const qc = useQueryClient()
  const { fetchMe } = useAuthStore()
  const [form, setForm] = useState({
    name: store.name || '',
    extension_price: store.extension_price || 2700,
    open_time: store.open_time || '19:00',
    close_time: store.close_time || '29:00',
  })

  const mutation = useMutation({
    mutationFn: () => apiClient.put(`/api/stores/${store.id}`, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stores-admin'] }); fetchMe(); onClose() },
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">店舗設定</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-3">
          <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" placeholder="店舗名" />
          <div>
            <label className="text-xs text-gray-400 block mb-1">延長料金（円）</label>
            <input type="number" value={form.extension_price} onChange={e => setForm({ ...form, extension_price: Number(e.target.value) })} className="input-field w-full" />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">営業開始時間</label>
            <TimeSelect value={form.open_time} onChange={v => setForm({ ...form, open_time: v })} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">営業終了時間（翌5:00 → 29:00）</label>
            <TimeSelect value={form.close_time} onChange={v => setForm({ ...form, close_time: v })} />
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.name} className="btn-primary flex-1">保存</button>
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
