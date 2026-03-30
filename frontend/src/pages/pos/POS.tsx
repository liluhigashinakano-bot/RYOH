import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, CreditCard, Banknote, Bot } from 'lucide-react'
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
    mutationFn: (data: { store_id: number; table_no: string }) =>
      apiClient.post('/api/tickets', data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId] })
      setShowNewTicket(false)
    },
  })

  return (
    <div className="space-y-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">POS・伝票管理</h1>
        <div className="flex items-center gap-3">
          {/* 店舗選択 */}
          <select
            value={selectedStoreId}
            onChange={(e) => setSelectedStoreId(Number(e.target.value))}
            className="input-field text-sm"
          >
            {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button onClick={() => setShowNewTicket(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            新規伝票
          </button>
        </div>
      </div>

      {/* リアルタイム売上バー */}
      <div className="card flex flex-wrap gap-4 text-sm">
        <div>
          <span className="text-gray-400">本日合計</span>
          <span className="ml-2 text-white font-bold text-lg">¥{(liveData?.total_amount ?? 0).toLocaleString()}</span>
        </div>
        <div>
          <span className="text-gray-400">会計済み</span>
          <span className="ml-2 text-green-400 font-medium">¥{(liveData?.closed_amount ?? 0).toLocaleString()}</span>
        </div>
        <div>
          <span className="text-gray-400">未会計</span>
          <span className="ml-2 text-yellow-400 font-medium">¥{(liveData?.open_amount ?? 0).toLocaleString()}</span>
          <span className="ml-1 text-gray-500">({liveData?.open_count ?? 0}卓)</span>
        </div>
      </div>

      {/* 伝票一覧 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {tickets.map((ticket: any) => (
          <TicketCard
            key={ticket.id}
            ticket={ticket}
            storeId={selectedStoreId}
            onClick={() => setSelectedTicketId(ticket.id)}
          />
        ))}
        {tickets.length === 0 && (
          <div className="col-span-full text-center text-gray-500 py-16">
            現在オープン中の伝票はありません
          </div>
        )}
      </div>

      {/* 新規伝票モーダル */}
      {showNewTicket && (
        <NewTicketModal
          storeId={selectedStoreId}
          onSubmit={(tableNo) => createMutation.mutate({ store_id: selectedStoreId, table_no: tableNo })}
          onClose={() => setShowNewTicket(false)}
        />
      )}

      {/* 伝票詳細モーダル */}
      {selectedTicketId && (
        <TicketDetailModal
          ticketId={selectedTicketId}
          storeId={selectedStoreId}
          onClose={() => setSelectedTicketId(null)}
        />
      )}
    </div>
  )
}

function TicketCard({ ticket, storeId, onClick }: { ticket: any; storeId: number; onClick: () => void }) {
  const elapsed = Math.floor((Date.now() - new Date(ticket.started_at).getTime()) / 60000)
  const hours = Math.floor(elapsed / 60)
  const mins = elapsed % 60

  return (
    <button
      onClick={onClick}
      className="card text-left space-y-3 hover:border-primary-600/50 transition-colors active:scale-95"
    >
      <div className="flex justify-between items-start">
        <div>
          <span className="text-xs text-gray-500">卓番</span>
          <p className="text-lg font-bold text-white">{ticket.table_no || '—'}</p>
        </div>
        <span className="badge bg-green-900/40 text-green-400">
          {hours > 0 ? `${hours}h` : ''}{mins}分
        </span>
      </div>
      <div>
        <p className="text-xs text-gray-400">延長 {ticket.extension_count}回</p>
        <p className="text-xl font-bold text-primary-400">¥{ticket.total_amount.toLocaleString()}</p>
      </div>
    </button>
  )
}

function NewTicketModal({ storeId, onSubmit, onClose }: { storeId: number; onSubmit: (t: string) => void; onClose: () => void }) {
  const [tableNo, setTableNo] = useState('')
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">新規伝票</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div>
          <label className="text-sm text-gray-400 block mb-1.5">卓番号</label>
          <input
            type="text"
            value={tableNo}
            onChange={e => setTableNo(e.target.value)}
            className="input-field w-full"
            placeholder="例: 1番、A卓"
            autoFocus
          />
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => onSubmit(tableNo)} className="btn-primary flex-1">開始</button>
        </div>
      </div>
    </div>
  )
}

function TicketDetailModal({ ticketId, storeId, onClose }: { ticketId: number; storeId: number; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: tickets } = useQuery({ queryKey: ['tickets', storeId, 'open'] })
  const ticket = (tickets as any[])?.find(t => t.id === ticketId)
  const [showClose, setShowClose] = useState(false)
  const [aiAdvice, setAiAdvice] = useState('')
  const [loadingAI, setLoadingAI] = useState(false)

  const addOrderMutation = useMutation({
    mutationFn: (item: { item_type: string; unit_price: number; quantity: number }) =>
      apiClient.post(`/api/tickets/${ticketId}/orders`, item).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tickets', storeId] }),
  })

  const closeMutation = useMutation({
    mutationFn: (data: any) => apiClient.post(`/api/tickets/${ticketId}/close`, data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tickets', storeId] }); onClose() },
  })

  const fetchAI = async () => {
    setLoadingAI(true)
    try {
      const res = await apiClient.post('/api/ai/rotation-advice', { store_id: storeId })
      setAiAdvice(res.data.advice)
    } catch { setAiAdvice('AIアドバイスを取得できませんでした') }
    setLoadingAI(false)
  }

  if (!ticket) return null

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-night-600 sticky top-0 bg-night-800">
          <div>
            <p className="text-sm text-gray-400">卓番</p>
            <h3 className="font-bold text-white text-lg">{ticket.table_no || '—'}</h3>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-400">合計</p>
            <p className="font-bold text-primary-400 text-xl">¥{ticket.total_amount.toLocaleString()}</p>
          </div>
          <button onClick={onClose} className="ml-4"><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* 注文ボタン */}
          <div>
            <p className="text-sm text-gray-400 mb-2">注文追加</p>
            <div className="grid grid-cols-2 gap-2">
              {ITEM_TYPES.map(({ type, label, defaultPrice }) => (
                <button
                  key={type}
                  onClick={() => addOrderMutation.mutate({ item_type: type, unit_price: defaultPrice, quantity: 1 })}
                  className="btn-secondary text-sm py-3 touch-target"
                >
                  {label}
                  {defaultPrice > 0 && <span className="block text-xs text-gray-500">¥{defaultPrice.toLocaleString()}</span>}
                </button>
              ))}
            </div>
          </div>

          {/* 付け回しAI */}
          <div className="border-t border-night-600 pt-4">
            <button
              onClick={fetchAI}
              disabled={loadingAI}
              className="flex items-center gap-2 text-primary-400 text-sm font-medium disabled:opacity-50"
            >
              <Bot className="w-4 h-4" />
              {loadingAI ? 'AI分析中...' : '付け回しAIアドバイス'}
            </button>
            {aiAdvice && (
              <div className="mt-2 p-3 bg-primary-900/20 border border-primary-800/40 rounded-xl text-sm text-gray-300 whitespace-pre-wrap">
                {aiAdvice}
              </div>
            )}
          </div>

          {/* 会計ボタン */}
          <div className="border-t border-night-600 pt-4 grid grid-cols-2 gap-3">
            <button
              onClick={() => closeMutation.mutate({ payment_method: 'cash', cash_amount: ticket.total_amount })}
              className="btn-secondary flex items-center justify-center gap-2 py-3"
            >
              <Banknote className="w-4 h-4" />
              現金会計
            </button>
            <button
              onClick={() => closeMutation.mutate({ payment_method: 'card', card_amount: ticket.total_amount })}
              className="btn-primary flex items-center justify-center gap-2 py-3"
            >
              <CreditCard className="w-4 h-4" />
              カード会計
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
