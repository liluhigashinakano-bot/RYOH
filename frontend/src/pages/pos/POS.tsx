import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, CreditCard, Banknote, Bot, Play, Pause } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

const ITEM_TYPES = [
  { type: 'extension', label: '延長', defaultPrice: 2700 },
  { type: 'drink_s', label: 'Sドリンク', defaultPrice: 900 },
  { type: 'drink_l', label: 'Lドリンク', defaultPrice: 1700 },
  { type: 'drink_mg', label: 'MGドリンク', defaultPrice: 3700 },
  { type: 'shot_cast', label: 'キャストショット', defaultPrice: 1500 },
  { type: 'shot_guest', label: 'ゲストショット', defaultPrice: 1000 },
  { type: 'champagne', label: 'シャンパン', defaultPrice: 0 },
  { type: 'other', label: 'その他', defaultPrice: 0 },
]

// キャストバックに影響するドリンク（キャスト選択が必要）
const CAST_SELECT_TYPES = new Set(['drink_l', 'drink_mg', 'shot_cast', 'champagne'])

// D時間の色設定
const DRINK_COLORS: Record<string, { label: string; color: string; bg: string }> = {
  drink_l:   { label: 'L',   color: 'text-cyan-400',   bg: 'bg-cyan-900/40' },
  drink_mg:  { label: 'MG',  color: 'text-purple-400', bg: 'bg-purple-900/40' },
  shot_cast: { label: 'S',   color: 'text-orange-400', bg: 'bg-orange-900/40' },
  champagne: { label: 'Ch',  color: 'text-yellow-400', bg: 'bg-yellow-900/40' },
}

const TABLE_NOS = [
  ...['A1','A2','A3','A4','A5','A6'],
  ...['B1','B2','B3','B4','B5','B6'],
  ...['C1','C2','C3','C4','C5','C6'],
]

function useNow() {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

function fmtTime(totalSec: number) {
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  if (h > 0) return `${h}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`
  return `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`
}

function toUtcMs(iso: string | null | undefined): number | null {
  if (!iso) return null
  const s = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z'
  return new Date(s).getTime()
}

function calcElapsed(startIso: string | null | undefined, now: number): number {
  const ms = toUtcMs(startIso)
  if (ms === null) return 0
  return Math.max(0, Math.floor((now - ms) / 1000))
}

function calcSetElapsed(ticket: any, now: number): number | null {
  const startMs = toUtcMs(ticket.set_started_at)
  if (startMs === null) return null
  const total = Math.floor((now - startMs) / 1000)
  const paused = ticket.set_paused_seconds || 0
  const pausedAtMs = toUtcMs(ticket.set_paused_at)
  const currentPause = ticket.set_is_paused && pausedAtMs
    ? Math.floor((now - pausedAtMs) / 1000)
    : 0
  return Math.max(0, total - paused - currentPause)
}

export default function POS() {
  const { stores } = useAuthStore()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)
  const [showNewTicket, setShowNewTicket] = useState(false)
  const [selectedTicketId, setSelectedTicketId] = useState<number | null>(null)
  const qc = useQueryClient()

  const { data: tickets = [] } = useQuery({
    queryKey: ['tickets', selectedStoreId, 'open'],
    queryFn: () => apiClient.get('/api/tickets', { params: { store_id: selectedStoreId, is_closed: false } }).then(r => r.data),
    enabled: !!selectedStoreId,
    refetchInterval: 15000,
  })

  const { data: liveData } = useQuery({
    queryKey: ['live', selectedStoreId],
    queryFn: () => apiClient.get(`/api/tickets/live/${selectedStoreId}`).then(r => r.data),
    enabled: !!selectedStoreId,
    refetchInterval: 15000,
  })

  const createMutation = useMutation({
    mutationFn: (data: { store_id: number; table_no: string; guest_count: number; plan_type: string; visit_type: string }) =>
      apiClient.post('/api/tickets', data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId] })
      setShowNewTicket(false)
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">POS・伝票管理</h1>
        <div className="flex items-center gap-3">
          <select value={selectedStoreId} onChange={(e) => setSelectedStoreId(Number(e.target.value))} className="input-field text-sm">
            {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button onClick={() => setShowNewTicket(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />新規伝票
          </button>
        </div>
      </div>

      <div className="card flex flex-wrap gap-4 text-sm">
        <div><span className="text-gray-400">本日合計</span><span className="ml-2 text-white font-bold text-lg">¥{(liveData?.total_amount ?? 0).toLocaleString()}</span></div>
        <div><span className="text-gray-400">会計済み</span><span className="ml-2 text-green-400 font-medium">¥{(liveData?.closed_amount ?? 0).toLocaleString()}</span></div>
        <div>
          <span className="text-gray-400">未会計</span>
          <span className="ml-2 text-yellow-400 font-medium">¥{(liveData?.open_amount ?? 0).toLocaleString()}</span>
          <span className="ml-1 text-gray-500">({liveData?.open_count ?? 0}卓)</span>
        </div>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-2" style={{ minHeight: '520px' }}>
        {tickets.map((ticket: any) => (
          <TicketCard key={ticket.id} ticket={ticket} storeId={selectedStoreId} onClick={() => setSelectedTicketId(ticket.id)} />
        ))}
        {tickets.length === 0 && (
          <div className="flex-1 text-center text-gray-500 py-16">現在オープン中の伝票はありません</div>
        )}
      </div>

      {showNewTicket && (
        <NewTicketModal
          storeId={selectedStoreId}
          onSubmit={(tableNo, guestCount, planType, visitType) =>
            createMutation.mutate({ store_id: selectedStoreId, table_no: tableNo, guest_count: guestCount, plan_type: planType, visit_type: visitType })
          }
          onClose={() => setShowNewTicket(false)}
        />
      )}

      {selectedTicketId && (
        <TicketDetailModal ticketId={selectedTicketId} storeId={selectedStoreId} onClose={() => setSelectedTicketId(null)} />
      )}
    </div>
  )
}

// D時間: 種別ごとに色分けして表示
function DrinkTimers({ lastDrinkTimes, now }: { lastDrinkTimes: any; now: number }) {
  if (!lastDrinkTimes) return <span className="text-gray-600 text-xs font-mono">D —</span>

  return (
    <div className="flex gap-2 flex-wrap">
      {Object.entries(DRINK_COLORS).map(([type, cfg]) => {
        const iso = lastDrinkTimes[type]
        const elapsed = iso ? calcElapsed(iso, now) : null
        return (
          <span key={type} className="flex items-center gap-1 text-xs font-mono">
            <span className={`${cfg.bg} ${cfg.color} px-1 rounded text-xs`}>{cfg.label}</span>
            <span className={elapsed !== null ? cfg.color : 'text-gray-600'}>
              {elapsed !== null ? fmtTime(elapsed) : '∞'}
            </span>
          </span>
        )
      })}
    </div>
  )
}

function TicketCard({ ticket, storeId, onClick }: { ticket: any; storeId: number; onClick: () => void }) {
  const now = useNow()
  const elapsed = calcElapsed(ticket.started_at, now)
  const setElapsed = calcSetElapsed(ticket, now)
  const eElapsed = ticket.e_started_at !== null ? calcElapsed(ticket.e_started_at, now) : null
  const startedAtMs = toUtcMs(ticket.started_at)
  const startedAt = startedAtMs ? new Date(startedAtMs) : new Date()

  return (
    <button
      onClick={onClick}
      className="card text-left flex flex-col hover:border-primary-600/50 transition-colors active:scale-95 shrink-0"
      style={{ width: '220px', minHeight: '480px' }}
    >
      {/* 卓番・経過時間 */}
      <div className="flex justify-between items-start mb-1">
        <p className="text-lg font-bold text-white">{ticket.table_no || '—'}</p>
        <span className="badge bg-green-900/40 text-green-400 font-mono text-xs">{fmtTime(elapsed)}</span>
      </div>

      {/* バッジ */}
      <div className="flex gap-1 flex-wrap mb-2">
        {ticket.visit_type && (
          <span className={`badge text-xs ${ticket.visit_type === 'N' ? 'bg-blue-900/40 text-blue-400' : 'bg-purple-900/40 text-purple-400'}`}>{ticket.visit_type}</span>
        )}
        {ticket.plan_type && (
          <span className={`badge text-xs ${ticket.plan_type === 'premium' ? 'bg-yellow-900/40 text-yellow-400' : 'bg-gray-700 text-gray-400'}`}>
            {ticket.plan_type === 'premium' ? 'プレミアム' : 'スタンダード'}
          </span>
        )}
        {ticket.guest_count > 0 && <span className="badge text-xs bg-night-600 text-gray-300">{ticket.guest_count}名</span>}
      </div>

      {/* 顧客・キャスト */}
      <div className="flex flex-col gap-0.5 text-xs mb-2">
        <span className="text-gray-400">{ticket.customer_name || '顧客未設定'}</span>
        <span className="text-primary-400">{ticket.current_cast_name || '担当未設定'}</span>
      </div>

      {/* E/SET タイマー */}
      <div className="flex gap-3 text-xs font-mono mb-1">
        <span className="text-gray-500">E <span className={eElapsed !== null ? 'text-orange-400' : 'text-gray-600'}>{eElapsed !== null ? fmtTime(eElapsed) : '—'}</span></span>
        {setElapsed !== null && (
          <span className="text-gray-500">SET <span className={ticket.set_is_paused ? 'text-yellow-400' : 'text-green-400'}>{fmtTime(setElapsed)}</span></span>
        )}
      </div>

      {/* D時間 */}
      <div className="mb-3">
        <DrinkTimers lastDrinkTimes={ticket.last_drink_times} now={now} />
      </div>

      {/* 注文明細 */}
      <div className="flex-1 border-t border-night-700 pt-2 mb-2">
        <p className="text-xs text-gray-500 mb-1">
          {startedAt.getHours().toString().padStart(2,'0')}:{startedAt.getMinutes().toString().padStart(2,'0')} 入店
        </p>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-600">
              <th className="text-left pb-1">品目</th>
              <th className="text-center pb-1">数</th>
              <th className="text-right pb-1">金額</th>
            </tr>
          </thead>
          <tbody>
            {(ticket.order_items || []).map((item: any) => (
              <tr key={item.id} className="border-t border-night-700/30">
                <td className="text-gray-300 py-0.5 truncate max-w-[90px]">{item.item_name}</td>
                <td className="text-center text-gray-500 py-0.5">{item.quantity}</td>
                <td className="text-right text-gray-300 py-0.5">¥{item.amount.toLocaleString()}</td>
              </tr>
            ))}
            {(!ticket.order_items || ticket.order_items.length === 0) && (
              <tr><td colSpan={3} className="text-gray-600 py-2">注文なし</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 合計 */}
      <div className="border-t border-night-600 pt-2">
        <p className="text-xs text-gray-400">延長 {ticket.extension_count}回</p>
        <p className="text-xl font-bold text-primary-400">¥{ticket.total_amount.toLocaleString()}</p>
      </div>
    </button>
  )
}

function NewTicketModal({ storeId, onSubmit, onClose }: {
  storeId: number
  onSubmit: (tableNo: string, guestCount: number, planType: string, visitType: string) => void
  onClose: () => void
}) {
  const [tableNo, setTableNo] = useState(TABLE_NOS[0])
  const [guestCount, setGuestCount] = useState(1)
  const [planType, setPlanType] = useState('premium')
  const [visitType, setVisitType] = useState('N')

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">新規伝票</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div>
          <label className="text-sm text-gray-400 block mb-1.5">卓番号</label>
          <select value={tableNo} onChange={e => setTableNo(e.target.value)} className="input-field w-full">
            {TABLE_NOS.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-sm text-gray-400 block mb-1.5">客数</label>
          <select value={guestCount} onChange={e => setGuestCount(Number(e.target.value))} className="input-field w-full">
            {Array.from({length: 20}, (_, i) => i + 1).map(n => <option key={n} value={n}>{n}名</option>)}
          </select>
        </div>
        <div>
          <label className="text-sm text-gray-400 block mb-1.5">プラン</label>
          <div className="flex gap-2">
            {['premium', 'standard'].map(p => (
              <button key={p} onClick={() => setPlanType(p)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${planType === p ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                {p === 'premium' ? 'プレミアム' : 'スタンダード'}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-sm text-gray-400 block mb-1.5">区分</label>
          <div className="flex gap-2">
            {['N', 'R'].map(v => (
              <button key={v} onClick={() => setVisitType(v)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${visitType === v ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                {v}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => onSubmit(tableNo, guestCount, planType, visitType)} className="btn-primary flex-1">開始</button>
        </div>
      </div>
    </div>
  )
}

// キャスト選択が必要な注文ボタンを押したときのモーダル
function CastSelectModal({ itemType, itemLabel, storeId, onSubmit, onClose }: {
  itemType: string
  itemLabel: string
  storeId: number
  onSubmit: (castId: number | null) => void
  onClose: () => void
}) {
  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const casts = (castsAll as any[]).filter((c: any) => c.is_active)
  const [castId, setCastId] = useState<number | null>(null)

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4">
      <div className="card w-full max-w-xs space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">{itemLabel} — キャスト選択</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div>
          <label className="text-sm text-gray-400 block mb-1.5">担当キャスト</label>
          <select value={castId ?? ''} onChange={e => setCastId(e.target.value ? Number(e.target.value) : null)} className="input-field w-full">
            <option value="">選択してください</option>
            {casts.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => onSubmit(castId)} disabled={!castId} className="btn-primary flex-1 disabled:opacity-40">追加</button>
        </div>
      </div>
    </div>
  )
}

function TicketDetailModal({ ticketId, storeId, onClose }: { ticketId: number; storeId: number; onClose: () => void }) {
  const qc = useQueryClient()
  const now = useNow()
  const [aiAdvice, setAiAdvice] = useState('')
  const [loadingAI, setLoadingAI] = useState(false)
  const [castSelectItem, setCastSelectItem] = useState<{ type: string; label: string; price: number } | null>(null)
  const prevSetIntervalRef = useRef<number>(-1)

  const { data: ticket, isLoading } = useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => apiClient.get(`/api/tickets/${ticketId}`).then(r => r.data),
    refetchInterval: 10000,
  })

  const addOrderMutation = useMutation({
    mutationFn: (item: { item_type: string; unit_price: number; quantity: number; cast_id?: number | null }) =>
      apiClient.post(`/api/tickets/${ticketId}/orders`, item).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
    },
  })

  const closeMutation = useMutation({
    mutationFn: (data: any) => apiClient.post(`/api/tickets/${ticketId}/close`, data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tickets', storeId] }); onClose() },
  })

  const setStartMutation = useMutation({
    mutationFn: () => apiClient.post(`/api/tickets/${ticketId}/set-start`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ticket', ticketId] }),
  })

  const setToggleMutation = useMutation({
    mutationFn: () => apiClient.post(`/api/tickets/${ticketId}/set-toggle`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ticket', ticketId] }),
  })

  // 40分ごと自動延長（人数分）
  useEffect(() => {
    if (!ticket || ticket.set_is_paused || !ticket.set_started_at) return
    const setElapsed = calcSetElapsed(ticket, now)
    if (setElapsed === null || setElapsed < 1) return
    const intervalNum = Math.floor(setElapsed / (40 * 60))
    if (intervalNum > 0 && intervalNum !== prevSetIntervalRef.current) {
      prevSetIntervalRef.current = intervalNum
      const guestCount = ticket.guest_count || 1
      const store = ticket.store_id
      // 延長料金を取得してから加算（storeのextension_priceを使用）
      apiClient.get(`/api/stores/${store}`).then(r => {
        const extPrice = r.data.extension_price || 2700
        for (let i = 0; i < guestCount; i++) {
          addOrderMutation.mutate({ item_type: 'extension', unit_price: extPrice, quantity: 1 })
        }
      })
    }
  }, [ticket, now])

  const handleItemClick = (type: string, label: string, price: number) => {
    if (CAST_SELECT_TYPES.has(type)) {
      setCastSelectItem({ type, label, price })
    } else {
      addOrderMutation.mutate({ item_type: type, unit_price: price, quantity: 1 })
    }
  }

  const fetchAI = async () => {
    setLoadingAI(true)
    try {
      const res = await apiClient.post('/api/ai/rotation-advice', { store_id: storeId })
      setAiAdvice(res.data.advice)
    } catch { setAiAdvice('AIアドバイスを取得できませんでした') }
    setLoadingAI(false)
  }

  if (isLoading || !ticket) return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="text-gray-400">読み込み中...</div>
    </div>
  )

  const elapsed = calcElapsed(ticket.started_at, now)
  const setElapsed = calcSetElapsed(ticket, now)
  const eElapsed = ticket.e_started_at ? calcElapsed(ticket.e_started_at, now) : null
  const startedAtMs = toUtcMs(ticket.started_at)
  const startedAt = startedAtMs ? new Date(startedAtMs) : new Date()

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-2 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-2xl w-full max-w-4xl h-[92vh] flex flex-col overflow-hidden">

        {/* ヘッダー */}
        <div className="px-4 py-3 border-b border-night-600 shrink-0 space-y-2">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <p className="text-xl font-bold text-white">{ticket.table_no || '—'}</p>
              <div className="flex gap-1.5 flex-wrap">
                {ticket.visit_type && (
                  <span className={`badge text-xs ${ticket.visit_type === 'N' ? 'bg-blue-900/40 text-blue-400' : 'bg-purple-900/40 text-purple-400'}`}>{ticket.visit_type}</span>
                )}
                {ticket.plan_type && (
                  <span className={`badge text-xs ${ticket.plan_type === 'premium' ? 'bg-yellow-900/40 text-yellow-400' : 'bg-gray-700 text-gray-300'}`}>
                    {ticket.plan_type === 'premium' ? 'プレミアム' : 'スタンダード'}
                  </span>
                )}
                {ticket.guest_count > 0 && <span className="badge text-xs bg-night-600 text-gray-300">{ticket.guest_count}名様</span>}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <p className="text-xl font-bold text-primary-400">¥{ticket.total_amount.toLocaleString()}</p>
              <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
            </div>
          </div>

          {/* タイマー行 */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <div className="flex gap-2 text-xs">
              <span className="text-gray-400">{ticket.customer_name || '顧客未設定'}</span>
              <span className="text-gray-600">/</span>
              <span className="text-primary-400">{ticket.current_cast_name || '担当未設定'}</span>
            </div>
            <div className="flex items-center gap-1 font-mono text-sm">
              <span className="text-gray-500 text-xs">経過</span>
              <span className="text-green-400">{fmtTime(elapsed)}</span>
            </div>
            <div className="flex items-center gap-1 font-mono text-sm">
              <span className="text-gray-500 text-xs">E</span>
              <span className={eElapsed !== null ? 'text-orange-400' : 'text-gray-600'}>{eElapsed !== null ? fmtTime(eElapsed) : '—'}</span>
            </div>

            {/* セットタイマー */}
            <div className="flex items-center gap-2 ml-auto">
              {!ticket.set_started_at ? (
                <button onClick={() => setStartMutation.mutate()} disabled={setStartMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1 bg-green-800/50 hover:bg-green-700/50 text-green-300 rounded-lg text-xs font-medium transition-colors">
                  <Play className="w-3 h-3" />セットスタート
                </button>
              ) : (
                <>
                  <span className="text-xs text-gray-500">SET</span>
                  <span className={`text-base font-bold font-mono ${ticket.set_is_paused ? 'text-yellow-400' : 'text-green-400'}`}>
                    {setElapsed !== null ? fmtTime(setElapsed) : '—'}
                  </span>
                  <button onClick={() => setToggleMutation.mutate()} disabled={setToggleMutation.isPending}
                    className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-colors ${
                      ticket.set_is_paused ? 'bg-green-800/50 hover:bg-green-700/50 text-green-300' : 'bg-yellow-800/50 hover:bg-yellow-700/50 text-yellow-300'
                    }`}>
                    {ticket.set_is_paused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                    {ticket.set_is_paused ? '再開' : '一時停止'}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* D時間（ドリンク別） */}
          <DrinkTimers lastDrinkTimes={ticket.last_drink_times} now={now} />
        </div>

        {/* 本体: 左(伝票) + 右(操作) */}
        <div className="flex flex-1 overflow-hidden">
          {/* 左: 伝票 */}
          <div className="w-1/2 border-r border-night-600 flex flex-col overflow-hidden">
            <div className="px-4 py-2 border-b border-night-700">
              <p className="text-xs text-gray-500">
                {startedAt.getHours().toString().padStart(2,'0')}:{startedAt.getMinutes().toString().padStart(2,'0')} 入店
              </p>
            </div>
            <div className="flex-1 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-night-800">
                  <tr className="text-xs text-gray-500 border-b border-night-700">
                    <th className="text-left px-4 py-2">ご注文</th>
                    <th className="text-center px-2 py-2">数</th>
                    <th className="text-right px-2 py-2">単価</th>
                    <th className="text-right px-4 py-2">金額</th>
                  </tr>
                </thead>
                <tbody>
                  {ticket.order_items?.map((item: any) => (
                    <tr key={item.id} className="border-b border-night-700/50">
                      <td className="px-4 py-2 text-gray-200">{item.item_name || item.item_type}</td>
                      <td className="text-center px-2 py-2 text-gray-400">{item.quantity}</td>
                      <td className="text-right px-2 py-2 text-gray-400">¥{item.unit_price.toLocaleString()}</td>
                      <td className="text-right px-4 py-2 text-white font-medium">¥{item.amount.toLocaleString()}</td>
                    </tr>
                  ))}
                  {(!ticket.order_items || ticket.order_items.length === 0) && (
                    <tr><td colSpan={4} className="text-center text-gray-600 py-8 text-sm">注文なし</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="border-t border-night-600 px-4 py-3 flex justify-between items-center">
              <span className="text-gray-400 text-sm">合計</span>
              <span className="text-primary-400 font-bold text-lg">¥{ticket.total_amount.toLocaleString()}</span>
            </div>
          </div>

          {/* 右: 操作 */}
          <div className="w-1/2 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              <p className="text-xs text-gray-500">注文追加</p>
              <div className="grid grid-cols-2 gap-2">
                {ITEM_TYPES.map(({ type, label, defaultPrice }) => (
                  <button key={type}
                    onClick={() => handleItemClick(type, label, defaultPrice)}
                    className={`btn-secondary text-sm py-3 ${CAST_SELECT_TYPES.has(type) ? 'border-primary-700/50' : ''}`}
                  >
                    {label}
                    {defaultPrice > 0 && <span className="block text-xs text-gray-500">¥{defaultPrice.toLocaleString()}</span>}
                    {CAST_SELECT_TYPES.has(type) && <span className="block text-xs text-primary-500">キャスト選択</span>}
                  </button>
                ))}
              </div>

              <div className="border-t border-night-700 pt-2">
                <button onClick={fetchAI} disabled={loadingAI}
                  className="flex items-center gap-2 text-primary-400 text-sm font-medium disabled:opacity-50">
                  <Bot className="w-4 h-4" />
                  {loadingAI ? 'AI分析中...' : '付け回しAIアドバイス'}
                </button>
                {aiAdvice && (
                  <div className="mt-2 p-3 bg-primary-900/20 border border-primary-800/40 rounded-xl text-xs text-gray-300 whitespace-pre-wrap">{aiAdvice}</div>
                )}
              </div>
            </div>

            <div className="border-t border-night-600 p-3 grid grid-cols-2 gap-3 shrink-0">
              <button onClick={() => closeMutation.mutate({ payment_method: 'cash', cash_amount: ticket.total_amount })}
                className="btn-secondary flex items-center justify-center gap-2 py-3">
                <Banknote className="w-4 h-4" />現金会計
              </button>
              <button onClick={() => closeMutation.mutate({ payment_method: 'card', card_amount: ticket.total_amount })}
                className="btn-primary flex items-center justify-center gap-2 py-3">
                <CreditCard className="w-4 h-4" />カード会計
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* キャスト選択モーダル */}
      {castSelectItem && (
        <CastSelectModal
          itemType={castSelectItem.type}
          itemLabel={castSelectItem.label}
          storeId={storeId}
          onSubmit={(castId) => {
            addOrderMutation.mutate({ item_type: castSelectItem.type, unit_price: castSelectItem.price, quantity: 1, cast_id: castId })
            setCastSelectItem(null)
          }}
          onClose={() => setCastSelectItem(null)}
        />
      )}
    </div>
  )
}
