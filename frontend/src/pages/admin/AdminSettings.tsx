import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Trash2, Edit2, Save, ChevronDown, ChevronUp } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

export default function AdminSettings() {
  const { stores } = useAuthStore()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">メニュー管理</h1>
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['menu-items', storeId] })
      qc.invalidateQueries({ queryKey: ['incentives', storeId] })
    },
  })

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiClient.put(`/api/app-settings/menu/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items', storeId] }),
  })

  return (
    <div className="card space-y-4">
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
                <th className="text-center py-2 px-2">キャスト</th>
                <th className="text-center py-2 px-2">インセン</th>
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
                    <span className={`badge text-xs ${item.has_incentive ? 'bg-yellow-900/40 text-yellow-400' : 'bg-night-700 text-gray-500'}`}>
                      {item.has_incentive ? 'あり' : 'なし'}
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
                  <td colSpan={6} className="text-center text-gray-600 py-6 text-sm">
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
  const [errorMsg, setErrorMsg] = useState('')
  const [form, setForm] = useState({
    label: item?.label || '',
    price: item?.price ?? 0,
    cast_required: item?.cast_required ?? true,
    has_incentive: item?.has_incentive ?? false,
    sort_order: item?.sort_order ?? 0,
  })

  const mutation = useMutation({
    mutationFn: () => item
      ? apiClient.put(`/api/app-settings/menu/${item.id}`, form)
      : apiClient.post('/api/app-settings/menu', { ...form, store_id: storeId, is_active: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['menu-items', storeId] })
      qc.invalidateQueries({ queryKey: ['incentives', storeId] })
      onClose()
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || '保存に失敗しました'
      setErrorMsg(String(msg))
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
              placeholder="例: オリジナルカクテル"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">単価（円）</label>
            <input
              type="number"
              value={form.price === 0 ? '' : form.price}
              onChange={e => setForm({ ...form, price: e.target.value === '' ? 0 : parseInt(e.target.value, 10) || 0 })}
              className="input-field w-full"
              min={0}
              placeholder="0"
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
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">インセンティブ</label>
            <div className="flex gap-2">
              {[true, false].map(v => (
                <button
                  key={String(v)}
                  onClick={() => setForm({ ...form, has_incentive: v })}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    form.has_incentive === v ? 'bg-yellow-700 text-white' : 'btn-secondary'
                  }`}
                >
                  {v ? 'あり' : 'なし'}
                </button>
              ))}
            </div>
            {form.has_incentive && (
              <p className="text-xs text-yellow-500/80 mt-1">
                インセンティブ率は下の「キャストドリンクインセンティブ率」で設定できます
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">表示順（小さいほど先頭）</label>
            <input
              type="number"
              value={form.sort_order}
              onChange={e => setForm({ ...form, sort_order: Number(e.target.value) })}
              onFocus={e => e.target.select()}
              className="input-field w-full"
              min={0}
            />
          </div>
        </div>
        {errorMsg && (
          <p className="text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
            エラー: {errorMsg}
          </p>
        )}
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => { setErrorMsg(''); mutation.mutate() }}
            disabled={!form.label.trim() || mutation.isPending}
            className="btn-primary flex-1 disabled:opacity-40"
          >
            {mutation.isPending ? '保存中...' : item ? '更新' : '追加'}
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
  const [localSettings, setLocalSettings] = useState<Record<string, { mode: string; rate: number; fixed: number }>>({})
  const [saved, setSaved] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const { data: incentives = [] } = useQuery({
    queryKey: ['incentives', storeId],
    queryFn: () => apiClient.get('/api/app-settings/incentives', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
  })

  useEffect(() => {
    if ((incentives as any[]).length > 0) {
      const map: Record<string, { mode: string; rate: number; fixed: number }> = {}
      ;(incentives as any[]).forEach((d: any) => {
        map[d.drink_type] = {
          mode: d.incentive_mode || 'percent',
          rate: d.rate ?? 10,
          fixed: d.fixed_amount ?? 0,
        }
      })
      setLocalSettings(map)
    }
  }, [storeId, JSON.stringify(incentives)])

  const saveMutation = useMutation({
    mutationFn: () => apiClient.put('/api/app-settings/incentives', {
      store_id: storeId,
      items: (incentives as any[]).map((d: any) => {
        const s = localSettings[d.drink_type] || { mode: 'percent', rate: 10, fixed: 0 }
        return {
          drink_type: d.drink_type,
          incentive_mode: s.mode,
          rate: s.rate,
          fixed_amount: s.mode === 'fixed' ? s.fixed : null,
        }
      }),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incentives', storeId] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const get = (drink_type: string) => localSettings[drink_type] || { mode: 'percent', rate: 10, fixed: 0 }
  const set = (drink_type: string, patch: Partial<{ mode: string; rate: number; fixed: number }>) => {
    setLocalSettings(prev => ({ ...prev, [drink_type]: { ...get(drink_type), ...patch } }))
  }

  return (
    <div className="card space-y-4">
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
            saved ? 'bg-green-700/40 text-green-400' : 'btn-primary'
          }`}
        >
          <Save className="w-3.5 h-3.5" />
          {saved ? '保存しました！' : '保存'}
        </button>
      </div>

      {!collapsed && (
        <>
          <p className="text-xs text-gray-500 -mt-2">日報でのキャストバック計算に使用します</p>

          <div className="space-y-0">
            {(incentives as any[]).map((d: any, i: number) => {
              const s = get(d.drink_type)
              const isLast = i === (incentives as any[]).length - 1
              const previewBack = s.mode === 'percent'
                ? Math.round((d.menu_price ?? d.price ?? 1700) * s.rate / 100)
                : s.fixed
              return (
                <div
                  key={d.drink_type}
                  className={`py-3 ${!isLast ? 'border-b border-night-700' : ''}`}
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <p className="text-white font-medium text-sm">{d.label}</p>
                      {d.is_custom && (
                        <span className="text-xs text-yellow-500/70">カスタムメニュー</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                      {/* モード切替 */}
                      <div className="flex rounded-lg overflow-hidden border border-night-600 text-xs">
                        <button
                          onClick={() => set(d.drink_type, { mode: 'percent' })}
                          className={`px-2.5 py-1.5 transition-colors ${s.mode === 'percent' ? 'bg-primary-600 text-white' : 'bg-night-800 text-gray-400 hover:text-white'}`}
                        >
                          ％
                        </button>
                        <button
                          onClick={() => set(d.drink_type, { mode: 'fixed' })}
                          className={`px-2.5 py-1.5 transition-colors ${s.mode === 'fixed' ? 'bg-primary-600 text-white' : 'bg-night-800 text-gray-400 hover:text-white'}`}
                        >
                          固定額
                        </button>
                      </div>

                      {/* 値入力 */}
                      {s.mode === 'percent' ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            value={s.rate}
                            onChange={e => set(d.drink_type, { rate: Number(e.target.value) })}
                            onFocus={e => e.target.select()}
                            className="input-field w-16 text-right text-sm"
                            min={0}
                            max={100}
                          />
                          <span className="text-gray-400 text-sm">%</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <span className="text-gray-400 text-sm">¥</span>
                          <input
                            type="number"
                            value={s.fixed}
                            onChange={e => set(d.drink_type, { fixed: Number(e.target.value) })}
                            onFocus={e => e.target.select()}
                            className="input-field w-20 text-right text-sm"
                            min={0}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                  {/* プレビュー */}
                  <p className="text-xs text-gray-600 mt-1 text-right">
                    → バック ¥{previewBack.toLocaleString()}
                  </p>
                </div>
              )
            })}

            {(incentives as any[]).length === 0 && (
              <p className="text-center text-gray-600 py-6 text-sm">設定がありません</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
