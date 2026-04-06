import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Trash2, Edit2, Save } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

type Tab = 'menu' | 'incentives'

const DRINK_TYPE_LABELS: Record<string, string> = {
  drink_l:   'Lドリンク',
  drink_mg:  'MGドリンク',
  drink_s:   'Sドリンク',
  shot_cast: 'キャストショット',
  champagne: 'シャンパン',
}

export default function AdminSettings() {
  const [tab, setTab] = useState<Tab>('menu')

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">管理設定</h1>

      <div className="flex gap-2">
        {(['menu', 'incentives'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
              tab === t ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400 hover:text-white'
            }`}
          >
            {t === 'menu' ? 'メニュー設定' : 'インセンティブ設定'}
          </button>
        ))}
      </div>

      {tab === 'menu' ? <MenuTab /> : <IncentivesTab />}
    </div>
  )
}

// ─────────────────────────────────────────
// メニュー設定タブ
// ─────────────────────────────────────────
function MenuTab() {
  const { stores } = useAuthStore()
  const qc = useQueryClient()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)
  const [showAdd, setShowAdd] = useState(false)
  const [editItem, setEditItem] = useState<any | null>(null)

  const { data: menuItems = [] } = useQuery({
    queryKey: ['menu-items', selectedStoreId],
    queryFn: () => apiClient.get('/api/app-settings/menu', { params: { store_id: selectedStoreId } }).then(r => r.data),
    enabled: !!selectedStoreId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/app-settings/menu/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items', selectedStoreId] }),
  })

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiClient.put(`/api/app-settings/menu/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items', selectedStoreId] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <select
            value={selectedStoreId}
            onChange={e => setSelectedStoreId(Number(e.target.value))}
            className="input-field text-sm"
          >
            {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <p className="text-gray-400 text-sm">{menuItems.length}件</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus className="w-4 h-4" />
          メニュー追加
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-night-600 text-gray-400">
              <th className="text-left py-2 px-3">メニュー名</th>
              <th className="text-right py-2 px-3">単価</th>
              <th className="text-center py-2 px-3">キャスト選択</th>
              <th className="text-center py-2 px-3">有効</th>
              <th className="py-2 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {(menuItems as any[]).map((item: any) => (
              <tr key={item.id} className="border-b border-night-700 hover:bg-night-700/50">
                <td className="py-2.5 px-3 font-medium text-white">{item.label}</td>
                <td className="py-2.5 px-3 text-right text-gray-300">¥{item.price.toLocaleString()}</td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`badge text-xs ${item.cast_required ? 'bg-purple-900/40 text-purple-400' : 'bg-night-700 text-gray-500'}`}>
                    {item.cast_required ? '必要' : 'なし'}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-center">
                  <button
                    onClick={() => toggleActive.mutate({ id: item.id, is_active: !item.is_active })}
                    className={`text-xs px-2 py-0.5 rounded-full transition-colors ${
                      item.is_active ? 'bg-green-900/40 text-green-400' : 'bg-night-700 text-gray-500'
                    }`}
                  >
                    {item.is_active ? '有効' : '無効'}
                  </button>
                </td>
                <td className="py-2.5 px-3">
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setEditItem(item)} className="text-gray-500 hover:text-primary-400 transition-colors">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => { if (confirm(`「${item.label}」を削除しますか？`)) deleteMutation.mutate(item.id) }}
                      className="text-gray-600 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {menuItems.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-gray-600 py-8">
                  メニューが登録されていません
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <MenuItemModal storeId={selectedStoreId} onClose={() => setShowAdd(false)} />
      )}
      {editItem && (
        <MenuItemModal storeId={selectedStoreId} item={editItem} onClose={() => setEditItem(null)} />
      )}
    </div>
  )
}

function MenuItemModal({ storeId, item, onClose }: { storeId: number; item?: any; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    label: item?.label || '',
    price: item?.price ?? 0,
    cast_required: item?.cast_required ?? true,
    sort_order: item?.sort_order ?? 0,
  })

  const mutation = useMutation({
    mutationFn: () => item
      ? apiClient.put(`/api/app-settings/menu/${item.id}`, form)
      : apiClient.post('/api/app-settings/menu', { ...form, store_id: storeId, is_active: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['menu-items', storeId] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">{item ? 'メニュー編集' : 'メニュー追加'}</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">メニュー名</label>
            <input
              value={form.label}
              onChange={e => setForm({ ...form, label: e.target.value })}
              className="input-field w-full"
              placeholder="例: Lドリンク"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">単価（円）</label>
            <input
              type="number"
              value={form.price}
              onChange={e => setForm({ ...form, price: Number(e.target.value) })}
              className="input-field w-full"
              min={0}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">キャスト選択</label>
            <div className="flex gap-2">
              {[true, false].map(v => (
                <button
                  key={String(v)}
                  onClick={() => setForm({ ...form, cast_required: v })}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    form.cast_required === v ? 'bg-primary-600 text-white' : 'btn-secondary'
                  }`}
                >
                  {v ? '必要' : 'なし'}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-1">
              「必要」にするとオーダー時にキャストを選択できます
            </p>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">表示順</label>
            <input
              type="number"
              value={form.sort_order}
              onChange={e => setForm({ ...form, sort_order: Number(e.target.value) })}
              className="input-field w-full"
              min={0}
            />
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!form.label}
            className="btn-primary flex-1 disabled:opacity-40"
          >
            {item ? '更新' : '追加'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────
// インセンティブ設定タブ
// ─────────────────────────────────────────
function IncentivesTab() {
  const { stores } = useAuthStore()
  const qc = useQueryClient()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)
  const [localRates, setLocalRates] = useState<Record<string, number>>({})
  const [saved, setSaved] = useState(false)

  const { data: incentives = [] } = useQuery({
    queryKey: ['incentives', selectedStoreId],
    queryFn: () => apiClient.get('/api/app-settings/incentives', { params: { store_id: selectedStoreId } }).then(r => r.data),
    enabled: !!selectedStoreId,
    onSuccess: (data: any[]) => {
      const map: Record<string, number> = {}
      data.forEach((d: any) => { map[d.drink_type] = d.rate })
      setLocalRates(map)
    },
  })

  const saveMutation = useMutation({
    mutationFn: () => apiClient.put('/api/app-settings/incentives', {
      store_id: selectedStoreId,
      items: Object.entries(localRates).map(([drink_type, rate]) => ({
        store_id: selectedStoreId,
        drink_type,
        rate,
      })),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incentives', selectedStoreId] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  // 店舗変更時にlocalRatesを同期
  const handleStoreChange = (id: number) => {
    setSelectedStoreId(id)
    setLocalRates({})
  }

  const getRate = (drink_type: string) => {
    if (localRates[drink_type] !== undefined) return localRates[drink_type]
    const found = (incentives as any[]).find((d: any) => d.drink_type === drink_type)
    return found?.rate ?? 10
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <select
          value={selectedStoreId}
          onChange={e => handleStoreChange(Number(e.target.value))}
          className="input-field text-sm"
        >
          {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="btn-primary flex items-center gap-2 text-sm"
        >
          <Save className="w-4 h-4" />
          {saved ? '保存しました！' : '保存'}
        </button>
      </div>

      <div className="card space-y-1">
        <p className="text-xs text-gray-500 mb-4">
          キャストドリンクのインセンティブ率（日報の計算に使用）
        </p>
        {(incentives as any[]).map((d: any) => (
          <div key={d.drink_type} className="flex items-center justify-between py-3 border-b border-night-700 last:border-0">
            <div>
              <p className="text-white font-medium text-sm">{d.label}</p>
              <p className="text-xs text-gray-500">{d.drink_type}</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={getRate(d.drink_type)}
                onChange={e => setLocalRates(prev => ({ ...prev, [d.drink_type]: Number(e.target.value) }))}
                className="input-field w-20 text-right text-sm"
                min={0}
                max={100}
              />
              <span className="text-gray-400 text-sm w-4">%</span>
            </div>
          </div>
        ))}
      </div>

      <div className="card bg-night-800/50 border border-night-600">
        <p className="text-xs text-gray-400">
          <span className="text-primary-400 font-medium">例）</span>
          Lドリンク ¥1,700、インセンティブ率 10% → キャストバック ¥170
        </p>
      </div>
    </div>
  )
}
