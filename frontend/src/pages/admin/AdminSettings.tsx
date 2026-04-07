import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Trash2, Edit2, Save, ChevronDown, ChevronUp } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

const DEFAULT_DRINK_TYPES = [
  { drink_type: 'drink_l',   label: 'Lドリンク' },
  { drink_type: 'drink_mg',  label: 'MGドリンク' },
  { drink_type: 'drink_s',   label: 'Sドリンク' },
  { drink_type: 'shot_cast', label: 'キャストショット' },
  { drink_type: 'champagne', label: 'シャンパン' },
]

export default function AdminSettings() {
  const { stores } = useAuthStore()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">管理設定</h1>
        <select
          value={selectedStoreId}
          onChange={e => setSelectedStoreId(Number(e.target.value))}
          className="input-field text-sm min-w-[120px]"
        >
          {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>

      {selectedStoreId ? (
        <StoreSettings storeId={selectedStoreId} />
      ) : (
        <p className="text-gray-500">店舗を選択してください</p>
      )}
    </div>
  )
}

// ─────────────────────────────────────────
// 店舗ごとの設定まとめ
// ─────────────────────────────────────────
function StoreSettings({ storeId }: { storeId: number }) {
  return (
    <div className="space-y-6">
      <MenuSection storeId={storeId} />
      <IncentiveSection storeId={storeId} />
    </div>
  )
}

// ─────────────────────────────────────────
// メニュー設定セクション
// ─────────────────────────────────────────
function MenuSection({ storeId }: { storeId: number }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editItem, setEditItem] = useState<any | null>(null)
  const [collapsed, setCollapsed] = useState(false)

  const { data: menuItems = [] } = useQuery({
    queryKey: ['menu-items', storeId],
    queryFn: () => apiClient.get('/api/app-settings/menu', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/app-settings/menu/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items', storeId] }),
  })

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiClient.put(`/api/app-settings/menu/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items', storeId] }),
  })

  return (
    <div className="card space-y-4">
      {/* セクションヘッダー */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCollapsed(v => !v)}
          className="flex items-center gap-2 text-white font-bold text-base"
        >
          {collapsed ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronUp className="w-4 h-4 text-gray-400" />}
          追加注文メニュー
          <span className="text-xs text-gray-500 font-normal ml-1">{(menuItems as any[]).length}件</span>
        </button>
        <button
          onClick={() => setShowAdd(true)}
          className="btn-primary flex items-center gap-1.5 text-sm py-1.5 px-3"
        >
          <Plus className="w-3.5 h-3.5" />メニュー追加
        </button>
      </div>

      {!collapsed && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-night-600 text-gray-400 text-xs">
                <th className="text-left py-2 px-2">メニュー名</th>
                <th className="text-right py-2 px-2">単価</th>
                <th className="text-center py-2 px-2">キャスト選択</th>
                <th className="text-center py-2 px-2">状態</th>
                <th className="py-2 px-2 w-16"></th>
              </tr>
            </thead>
            <tbody>
              {(menuItems as any[]).map((item: any) => (
                <tr key={item.id} className="border-b border-night-700 hover:bg-night-700/30">
                  <td className="py-2.5 px-2 font-medium text-white">{item.label}</td>
                  <td className="py-2.5 px-2 text-right text-gray-300">¥{item.price.toLocaleString()}</td>
                  <td className="py-2.5 px-2 text-center">
                    <span className={`badge text-xs ${item.cast_required ? 'bg-purple-900/40 text-purple-400' : 'bg-night-700 text-gray-500'}`}>
                      {item.cast_required ? '必要' : 'なし'}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <button
                      onClick={() => toggleActive.mutate({ id: item.id, is_active: !item.is_active })}
                      className={`text-xs px-2 py-0.5 rounded-full transition-colors ${
                        item.is_active ? 'bg-green-900/40 text-green-400' : 'bg-night-700 text-gray-500'
                      }`}
                    >
                      {item.is_active ? '有効' : '無効'}
                    </button>
                  </td>
                  <td className="py-2.5 px-2">
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => setEditItem(item)} className="text-gray-500 hover:text-primary-400 transition-colors">
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => { if (confirm(`「${item.label}」を削除しますか？`)) deleteMutation.mutate(item.id) }}
                        className="text-gray-600 hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(menuItems as any[]).length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center text-gray-600 py-6 text-sm">
                    メニューが登録されていません
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && <MenuItemModal storeId={storeId} onClose={() => setShowAdd(false)} />}
      {editItem && <MenuItemModal storeId={storeId} item={editItem} onClose={() => setEditItem(null)} />}
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
            <label className="text-xs text-gray-400 block mb-1">表示順（小さいほど先頭）</label>
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
            disabled={!form.label || mutation.isPending}
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
// インセンティブ設定セクション
// ─────────────────────────────────────────
function IncentiveSection({ storeId }: { storeId: number }) {
  const qc = useQueryClient()
  const [localRates, setLocalRates] = useState<Record<string, number>>({})
  const [saved, setSaved] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const { data: incentives = [] } = useQuery({
    queryKey: ['incentives', storeId],
    queryFn: () => apiClient.get('/api/app-settings/incentives', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
  })

  // incentivesが読み込まれたらlocalRatesに反映
  useEffect(() => {
    if ((incentives as any[]).length > 0) {
      const map: Record<string, number> = {}
      ;(incentives as any[]).forEach((d: any) => { map[d.drink_type] = d.rate })
      setLocalRates(map)
    }
  }, [storeId, JSON.stringify(incentives)])

  const saveMutation = useMutation({
    mutationFn: () => apiClient.put('/api/app-settings/incentives', {
      store_id: storeId,
      items: DEFAULT_DRINK_TYPES.map(d => ({
        store_id: storeId,
        drink_type: d.drink_type,
        rate: localRates[d.drink_type] ?? 10,
      })),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incentives', storeId] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const getRate = (drink_type: string) => localRates[drink_type] ?? 10

  return (
    <div className="card space-y-4">
      {/* セクションヘッダー */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCollapsed(v => !v)}
          className="flex items-center gap-2 text-white font-bold text-base"
        >
          {collapsed ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronUp className="w-4 h-4 text-gray-400" />}
          キャストドリンク インセンティブ率
        </button>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className={`flex items-center gap-1.5 text-sm py-1.5 px-3 rounded-xl font-medium transition-colors ${
            saved
              ? 'bg-green-700/40 text-green-400'
              : 'btn-primary'
          }`}
        >
          <Save className="w-3.5 h-3.5" />
          {saved ? '保存しました！' : '保存'}
        </button>
      </div>

      {!collapsed && (
        <>
          <p className="text-xs text-gray-500 -mt-2">
            日報でのキャストバック計算に使用します
          </p>

          <div className="space-y-0">
            {DEFAULT_DRINK_TYPES.map((d, i) => (
              <div
                key={d.drink_type}
                className={`flex items-center justify-between py-3 ${i < DEFAULT_DRINK_TYPES.length - 1 ? 'border-b border-night-700' : ''}`}
              >
                <div>
                  <p className="text-white font-medium text-sm">{d.label}</p>
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

          <div className="bg-night-900/60 border border-night-600 rounded-xl p-3">
            <p className="text-xs text-gray-400">
              <span className="text-primary-400 font-medium">計算例）</span>
              Lドリンク ¥1,700、インセンティブ率 {getRate('drink_l')}% → キャストバック ¥{Math.round(1700 * getRate('drink_l') / 100).toLocaleString()}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
