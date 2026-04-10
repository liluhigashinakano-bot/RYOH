import React, { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, CreditCard, Banknote, Bot, Play, Pause, QrCode, ClipboardList, Pencil } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'
import DailyReportPanel from './DailyReportPanel'

const ITEM_TYPE_LABELS: Record<string, string> = {
  extension: '延長', drink_s: 'Sドリンク', drink_l: 'Lドリンク',
  drink_mg: 'MGドリンク', shot_cast: 'キャストショット', shot_guest: 'ゲストショット',
  champagne: 'シャンパン', set: 'セット料金', other: 'その他', custom_menu: 'カスタムメニュー',
}

function displayItemName(item: any, castMap?: Record<number, string>): string {
  const raw = item.item_name || item.item_type || ''
  // item_nameがitem_typeコード（英語）のままの場合も日本語ラベルに変換
  const base = ITEM_TYPE_LABELS[raw] ?? raw
  if (castMap && item.cast_id && castMap[item.cast_id] && !base.includes('［')) {
    return `${base}［${castMap[item.cast_id]}］`
  }
  return base
}

const CHAMPAGNE_MENU = [
  { name: 'ヴーヴイエロー', price: 26000 },
  { name: 'ヴーヴホワイト', price: 28000 },
  { name: 'ヴーヴリッチ', price: 37000 },
  { name: 'ヴーヴリッチロゼ', price: 35000 },
  { name: 'モエアイス', price: 30000 },
  { name: 'モエアイスロゼ', price: 35000 },
  { name: 'ペリエジュエベルエポック', price: 80000 },
  { name: 'アルマンドブリニャック', price: 150000 },
  { name: 'エンジェルブラック', price: 120000 },
  { name: 'エンジェルホワイト', price: 200000 },
  { name: '1688ノンアル', price: 20000 },
  { name: 'シャメイ', price: 10000 },
  { name: 'ノンアルオリシャン', price: 30000 },
  { name: 'オリシャン', price: 20000 },
  { name: '光オリシャン', price: 50000 },
]

const ITEM_TYPES = [
  { type: 'drink_s', label: 'Sドリンク', defaultPrice: 900 },
  { type: 'drink_l', label: 'Lドリンク', defaultPrice: 1700 },
  { type: 'drink_mg', label: 'MGドリンク', defaultPrice: 3700 },
  { type: 'shot_cast', label: 'キャストショット', defaultPrice: 1500 },
  { type: 'shot_guest', label: 'ゲストショット', defaultPrice: 1000 },
  { type: 'champagne', label: 'シャンパン', defaultPrice: 0 },
  { type: 'other', label: 'その他', defaultPrice: 0 },
]

// キャストバックに影響するドリンク（キャスト選択が必要）
const CAST_SELECT_TYPES = new Set(['drink_s', 'drink_l', 'drink_mg', 'shot_cast', 'champagne'])

// D時間の色設定（shot_castは除外、drink_sを追加）
const DRINK_COLORS: Record<string, { label: string; color: string; bg: string }> = {
  drink_s:     { label: 'S',   color: 'text-green-400',  bg: 'bg-green-900/40' },
  drink_l:     { label: 'L',   color: 'text-cyan-400',   bg: 'bg-cyan-900/40' },
  drink_mg:    { label: 'MG',  color: 'text-purple-400', bg: 'bg-purple-900/40' },
  champagne:   { label: 'Ch',  color: 'text-yellow-400', bg: 'bg-yellow-900/40' },
  custom_menu: { label: 'CM',  color: 'text-orange-400', bg: 'bg-orange-900/40' },
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

// チケットのgrandTotal（税サ込み・先会計前の全額）を計算
function calcTicketGrandTotal(ticket: any): number {
  const sk = (ticket.order_items || [])
    .filter((i: any) => (i.item_name?.startsWith('先会計') || i.item_name?.startsWith('分割清算') || i.item_name?.startsWith('値引き')) && !i.canceled_at)
    .reduce((s: number, i: any) => s + Math.abs(i.amount), 0)
  const sub = ticket.total_amount + sk
  return Math.round(sub * 1.21)
}

// 0〜5時 → 24〜29時に変換（バー営業時間表記）
function toBarHour(h: number) { return h < 12 ? h + 24 : h }
function fromBarHour(h: number) { return h >= 24 ? h - 24 : h }
// 19〜29の時間選択肢
const BAR_HOURS = Array.from({ length: 11 }, (_, i) => i + 19)

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

const SET_DURATION = 40 * 60 // 40分

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

// 現在セット内の残り秒数（0～SET_DURATION）
function calcSetCountdown(setElapsed: number | null): number | null {
  if (setElapsed === null) return null
  const withinSet = setElapsed % SET_DURATION
  return SET_DURATION - withinSet
}

// 何セット目か（1始まり）
function calcSetInterval(setElapsed: number | null): number {
  if (setElapsed === null) return 0
  return Math.floor(setElapsed / SET_DURATION)
}

function AutoExtender({ ticket, storeId, extensionPrice: _ }: { ticket: any; storeId: number; extensionPrice: number }) {
  const qc = useQueryClient()
  const now = useNow()
  const inflightRef = useRef<Set<number>>(new Set())

  useEffect(() => {
    if (!ticket || ticket.set_is_paused || !ticket.set_started_at) return
    const setElapsed = calcSetElapsed(ticket, now)
    if (setElapsed === null) return
    // 期番号 = 経過秒 / 2400 (40分)。0 始まり → 1 以上が延長対象
    // intervalNum (calcSetInterval) と等価
    const periodCount = calcSetInterval(setElapsed)
    if (periodCount <= 0) return

    const dbPeriod = ticket.extension_count || 0
    if (periodCount <= dbPeriod) return

    // 不足期を順に period_no 指定で追加（重複は backend が弾く）
    const extPrice = ticket.plan_type === 'premium' ? 4000 : 3000
    for (let p = dbPeriod + 1; p <= periodCount; p++) {
      if (inflightRef.current.has(p)) continue
      inflightRef.current.add(p)
      apiClient.post(`/api/tickets/${ticket.id}/orders`, {
        item_type: 'extension',
        unit_price: extPrice,
        quantity: 1,
        period_no: p,
      }).then(() => {
        qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
        qc.invalidateQueries({ queryKey: ['ticket', ticket.id] })
      }).finally(() => {
        inflightRef.current.delete(p)
      })
    }
  }, [ticket, now])

  return null
}

const JOIN_DURATION = 40 * 60 * 1000  // 40分

function JoinAutoExtender({ ticket, storeId }: { ticket: any; storeId: number }) {
  const qc = useQueryClient()
  useNow()  // 1秒ごとに再レンダリングさせるためだけに使用
  // 各 join item の最後に発火した時刻（UNIX ms）。連続発火の安全弁。
  const lastFireRef = useRef<Record<number, number>>({})
  // マウント時刻。これより前の合流は「過去分」として無視する（リロード時の暴走防止）
  const mountedAtRef = useRef<number>(Date.now())
  // 各 join item をマウント時刻基準で初回処理した intervalNum（マウント以降の経過分のみ加算）
  const baselineRef = useRef<Record<number, number>>({})
  const inflightRef = useRef<Set<number>>(new Set())

  useEffect(() => {
    if (!ticket || ticket.is_closed) return
    const joinItems = (ticket.order_items || []).filter((i: any) =>
      i.item_name && i.item_name.includes('合流') && i.created_at
    )
    if (!joinItems.length) return

    const nowMs = Date.now()
    for (const item of joinItems) {
      // 初回観測時のベースラインを必ず記録
      const startMs = new Date(item.created_at.endsWith('Z') ? item.created_at : item.created_at + 'Z').getTime()
      const elapsed = nowMs - startMs
      const intervalNum = Math.floor(elapsed / JOIN_DURATION)

      if (baselineRef.current[item.id] === undefined) {
        baselineRef.current[item.id] = intervalNum
        continue
      }
      if (intervalNum <= baselineRef.current[item.id]) continue

      // 連続発火の安全弁: 同じ id で前回 fire してから 60 秒空ける
      const lastFire = lastFireRef.current[item.id] || 0
      if (nowMs - lastFire < 60_000) continue
      // in-flight guard: 同時並行の POST を防ぐ
      if (inflightRef.current.has(item.id)) continue

      lastFireRef.current[item.id] = nowMs
      inflightRef.current.add(item.id)
      baselineRef.current[item.id] = intervalNum

      const isPremium = item.item_name.includes('プレミアム')
      const extPrice = isPremium ? 4000 : 3000
      const extName = isPremium ? '合流延長（プレミアム）' : '合流延長（スタンダード）'
      const existing = (ticket.order_items ?? []).find((oi: any) => !oi.canceled_at && oi.item_type === 'extension' && oi.item_name === extName)
      const req = existing
        ? apiClient.patch(`/api/tickets/orders/${existing.id}`, { quantity: existing.quantity + 1 })
        : apiClient.post(`/api/tickets/${ticket.id}/orders`, { item_type: 'extension', item_name: extName, unit_price: extPrice, quantity: 1 })
      req.then(() => {
        qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
        qc.invalidateQueries({ queryKey: ['ticket', ticket.id] })
      }).finally(() => {
        inflightRef.current.delete(item.id)
      })
    }
  }, [ticket?.id, ticket?.order_items?.length])

  return null
}

export default function POS() {
  const { stores } = useAuthStore()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)
  const [showNewTicket, setShowNewTicket] = useState(false)
  const [showTissueStartModal, setShowTissueStartModal] = useState(false)
  const [showAIAdvisor, setShowAIAdvisor] = useState(false)
  const [aiAdvisorLoading, setAIAdvisorLoading] = useState(false)
  const [aiAdvisorResult, setAIAdvisorResult] = useState<any>(null)
  const [aiAdvisorError, setAIAdvisorError] = useState<string>('')
  const [aiAdvisorHistory, setAIAdvisorHistory] = useState<any[]>([])
  const [aiAdvisorTab, setAIAdvisorTab] = useState<'current' | 'history'>('current')
  const [selectedTicketId, setSelectedTicketId] = useState<number | null>(null)
  const [view, setView] = useState<'open' | 'attendance' | 'history' | 'logs' | 'reports' | 'casts'>('open')
  const [showOpenSessionModal, setShowOpenSessionModal] = useState(false)
  const [showCloseSessionModal, setShowCloseSessionModal] = useState(false)
  const [showSessionThanks, setShowSessionThanks] = useState(false)
  const [showOpenTicketAlert, setShowOpenTicketAlert] = useState(false)
  // 営業終了モーダルの入力値を保持（閉じても消えないように）
  const [closeModalExpenses, setCloseModalExpenses] = useState<ExpenseRow[]>([
    { id: 1, type: 'liquor', category: '田野屋', amount: '' },
    { id: 2, type: 'other', category: '', amount: '' },
  ])
  const [closeModalWithdrawals, setCloseModalWithdrawals] = useState<{ id: number; type: string; name: string; amount: string }[]>([
    { id: 1, type: '', name: '', amount: '' },
  ])
  const [closeModalNotes, setCloseModalNotes] = useState('')
  // カード上の顧客・キャストモーダルをPOSPage レベルで管理（TicketCard内の event propagation 問題を回避）
  const [customerModalTicket, setCustomerModalTicket] = useState<any | null>(null)
  const [castModalTicket, setCastModalTicket] = useState<any | null>(null)
  const [activeCastsModalTicket, setActiveCastsModalTicket] = useState<any | null>(null)
  const dragFromIdxRef = useRef<number | null>(null)
  const qc = useQueryClient()

  const { data: tickets = [] } = useQuery({
    queryKey: ['tickets', selectedStoreId, 'open'],
    queryFn: () => apiClient.get('/api/tickets', { params: { store_id: selectedStoreId, is_closed: false } }).then(r => r.data),
    enabled: !!selectedStoreId,
    refetchInterval: 15000,
  })

  const { data: storeInfo } = useQuery({
    queryKey: ['store', selectedStoreId],
    queryFn: () => apiClient.get(`/api/stores/${selectedStoreId}`).then(r => r.data),
    enabled: !!selectedStoreId,
  })

  // 天気 + 鉄道（POS用）
  const POS_STORE_COORDS: Record<string, { lat: number; lon: number; lines: string[] }> = {
    higashinakano: { lat: 35.7075, lon: 139.6782, lines: ['中央総武線', '中央線(快速)', '総武線(快速)', '都営大江戸線'] },
    shinnakano: { lat: 35.6975, lon: 139.6615, lines: ['東京メトロ丸ノ内線'] },
    honancho: { lat: 35.6835, lon: 139.6480, lines: ['東京メトロ丸ノ内線'] },
  }
  const posStoreCode = (storeInfo as any)?.code || ''
  const posCoords = POS_STORE_COORDS[posStoreCode]
  const WMO: Record<number, string> = { 0:'☀️',1:'🌤️',2:'⛅',3:'☁️',45:'🌫️',48:'🌫️',51:'🌦️',53:'🌦️',55:'🌧️',61:'🌧️',63:'🌧️',65:'🌧️',71:'🌨️',73:'🌨️',75:'❄️',80:'🌦️',81:'🌧️',82:'⛈️',95:'⛈️',96:'⛈️',99:'⛈️' }

  const { data: posWeather } = useQuery({
    queryKey: ['pos-weather', posCoords?.lat, posCoords?.lon],
    queryFn: async () => {
      if (!posCoords) return null
      const r = await import('axios').then(m => m.default.get('https://api.open-meteo.com/v1/forecast', {
        params: { latitude: posCoords.lat, longitude: posCoords.lon, hourly: 'temperature_2m,weathercode,windspeed_10m', timezone: 'Asia/Tokyo', forecast_days: 2 },
      }))
      return r.data
    },
    enabled: !!posCoords,
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
  })
  const { data: posTrainRaw } = useQuery({
    queryKey: ['pos-train'],
    queryFn: () => apiClient.get('/api/train-info').then(r => r.data),
    staleTime: 1000 * 60 * 5,
    refetchInterval: 1000 * 60 * 5,
  })
  const posTrainLines: any[] = ((posTrainRaw as any)?.lines ?? []).filter((t: any) => posCoords?.lines.some((rl: string) => t.line.includes(rl) || rl.includes(t.line)))
  const posLastTrains: any[] = ((posTrainRaw as any)?.last_trains ?? []).filter((t: any) => t.store === posStoreCode && t.arrive)
  const posCurrentWeather = (() => {
    if (!posWeather?.hourly) return null
    const h = posWeather.hourly
    const now = new Date()
    const idx = h.time.findIndex((t: string) => new Date(t) >= now)
    if (idx < 0) return null
    return { temp: Math.round(h.temperature_2m[idx]), icon: WMO[h.weathercode[idx]] || '❓', wind: Math.round(h.windspeed_10m[idx]) }
  })()

  const { data: currentSession } = useQuery({
    queryKey: ['session', selectedStoreId],
    queryFn: () => apiClient.get('/api/sessions/current', { params: { store_id: selectedStoreId } }).then(r => r.data),
    enabled: !!selectedStoreId,
    refetchInterval: 30000,
  })

  const { data: liveData } = useQuery({
    queryKey: ['live', selectedStoreId, currentSession?.opened_at ?? null],
    queryFn: () => apiClient.get(`/api/tickets/live/${selectedStoreId}`, {
      params: currentSession?.opened_at ? { session_opened_at: currentSession.opened_at } : {},
    }).then(r => r.data),
    enabled: !!selectedStoreId,
    refetchInterval: 15000,
  })

  const { data: lastClosedSession } = useQuery({
    queryKey: ['session-last-closed', selectedStoreId],
    queryFn: () => apiClient.get('/api/sessions/last-closed', { params: { store_id: selectedStoreId } }).then(r => r.data),
    enabled: !!selectedStoreId && showOpenSessionModal,
  })

  const openSessionMutation = useMutation({
    mutationFn: (d: { opening_cash: number; opening_cash_detail: Record<string, number>; prev_day_diff: number; operator_name?: string; event_name?: string; notes?: string }) =>
      apiClient.post('/api/sessions/open', { store_id: selectedStoreId, ...d }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['session', selectedStoreId] })
      setShowOpenSessionModal(false)
      // 営業開始時に前日の締め作業入力をリセット
      setCloseModalExpenses([
        { id: 1, type: 'liquor', category: '田野屋', amount: '' },
        { id: 2, type: 'other', category: '', amount: '' },
      ])
      setCloseModalWithdrawals([{ id: 1, type: '', name: '', amount: '' }])
      setCloseModalNotes('')
    },
  })

  const closeSessionMutation = useMutation({
    mutationFn: (d: { closing_cash: number; closing_cash_detail: Record<string, number>; notes?: string; cash_diff?: number | null; expenses_detail?: any; cash_sales?: number; card_sales?: number; code_sales?: number }) =>
      apiClient.post(`/api/sessions/${currentSession?.id}/close`, d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['session', selectedStoreId] })
      qc.invalidateQueries({ queryKey: ['session-list', selectedStoreId] })
      qc.invalidateQueries({ queryKey: ['attendance', selectedStoreId] })
      qc.invalidateQueries({ queryKey: ['staff-attendance', selectedStoreId] })
      setShowCloseSessionModal(false)
      setShowSessionThanks(true)
      setTimeout(() => setShowSessionThanks(false), 4000)
    },
  })
  const extensionPrice: number = storeInfo?.extension_price || 2700

  const createMutation = useMutation({
    mutationFn: (data: { store_id: number; table_no: string; guest_count: number; plan_type: string; visit_type: string; visit_motivation?: string; motivation_cast_id?: number | null; motivation_note?: string }) =>
      apiClient.post('/api/tickets', data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId] })
      setShowNewTicket(false)
    },
  })

  return (
    <div className="flex flex-col" style={{ height: '100%', paddingBottom: '12px' }}>
      {/* ヘッダー */}
      <div className="shrink-0 pb-2 flex flex-col gap-1.5">
        {/* Row 1: 店舗・新規伝票 + 営業ボタン */}
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold text-white shrink-0 hidden md:block">POS・伝票管理</h1>
          <select value={selectedStoreId} onChange={(e) => setSelectedStoreId(Number(e.target.value))} className="input-field text-xs py-1.5 shrink-0">
            {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {view === 'open' && (
            <button
              onClick={() => {
                if (!currentSession) {
                  alert('営業が開始されていません。\n先に「営業開始」を行ってください。')
                  return
                }
                setShowNewTicket(true)
              }}
              className="btn-primary flex items-center gap-1 text-xs px-2.5 py-1.5 whitespace-nowrap shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />新規伝票
            </button>
          )}
          {currentSession && !currentSession.is_closed && (
            <button
              onClick={() => setShowTissueStartModal(true)}
              className="bg-amber-700 hover:bg-amber-600 text-white text-xs px-2.5 py-1.5 rounded-lg whitespace-nowrap shrink-0"
            >
              ティッシュ配り
            </button>
          )}
          {currentSession && !currentSession.is_closed && (
            <button
              onClick={async () => {
                setShowAIAdvisor(true)
                setAIAdvisorLoading(true)
                setAIAdvisorError('')
                setAIAdvisorResult(null)
                try {
                  const r = await apiClient.post(`/api/ai/suggest-rotation/${selectedStoreId}`)
                  setAIAdvisorResult(r.data)
                } catch (e: any) {
                  setAIAdvisorError(e?.response?.data?.detail || e?.message || 'エラーが発生しました')
                } finally {
                  setAIAdvisorLoading(false)
                }
              }}
              className="bg-pink-800 hover:bg-pink-700 text-white text-xs px-2.5 py-1.5 rounded-lg whitespace-nowrap shrink-0 border border-pink-500/50"
            >
              🤖 付け回しAIアドバイス
            </button>
          )}
          {/* 右: 売上サマリ + 営業ボタン */}
          <div className="flex items-center gap-2 ml-auto shrink-0">
            <div className="hidden md:flex items-center gap-3 text-xs">
              <div><span className="text-gray-500">合計</span><span className="ml-1 text-white font-bold">¥{(currentSession ? (liveData?.total_amount ?? 0) : 0).toLocaleString()}</span></div>
              <div><span className="text-gray-500">未会計</span><span className="ml-1 text-yellow-400 font-medium">¥{(currentSession ? (liveData?.open_amount ?? 0) : 0).toLocaleString()}</span><span className="ml-1 text-gray-600">({currentSession ? (liveData?.open_count ?? 0) : 0}卓)</span></div>
            </div>
            {currentSession && !currentSession.is_closed ? (
              <button onClick={() => setShowCloseSessionModal(true)}
                className="btn-danger text-xs px-3 py-1.5 whitespace-nowrap shrink-0">
                営業締め作業
              </button>
            ) : (
              <button onClick={() => setShowOpenSessionModal(true)}
                className="bg-green-700 hover:bg-green-600 active:bg-green-800 text-white font-medium px-3 py-1.5 rounded-lg transition-colors text-xs whitespace-nowrap shrink-0">
                営業開始
              </button>
            )}
          </div>
        </div>
        {/* Row 2: ナビタブ（横スクロール対応） */}
        <div className="overflow-x-auto">
          <div className="flex bg-gray-800 rounded-lg p-0.5 gap-0.5 min-w-max">
            <button onClick={() => setView('open')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${view === 'open' ? 'bg-pink-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              オープン中
            </button>
            <button onClick={() => setView('casts')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${view === 'casts' ? 'bg-purple-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              対応中キャスト
            </button>
            <button onClick={() => setView('attendance')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${view === 'attendance' ? 'bg-emerald-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              従業員勤怠
            </button>
            <button onClick={() => setView('history')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${view === 'history' ? 'bg-pink-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              会計済み
            </button>
            <button onClick={() => setView('logs')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${view === 'logs' ? 'bg-orange-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              変更履歴
            </button>
            <button onClick={() => setView('reports')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors whitespace-nowrap ${view === 'reports' ? 'bg-blue-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              日報一覧
            </button>
            {/* 天気+運行情報(遅延/運休のみ)+終電 */}
            <div className="ml-auto flex items-center gap-2 text-[10px] shrink-0 pl-3">
              {posCurrentWeather && (
                <span className="text-gray-300">{posCurrentWeather.icon}{posCurrentWeather.temp}° 風{posCurrentWeather.wind}</span>
              )}
              {posTrainLines.filter((t: any) => t.status !== 'normal').map((t: any) => (
                <span key={t.line} className={t.status === 'delay' ? 'text-yellow-400' : 'text-red-400'}>
                  {t.line.replace(/\[.*\]/, '').replace('東京メトロ', '').replace('都営', '')}
                  {t.status === 'delay' ? '⚠遅延' : '🚫運休'}
                </span>
              ))}
              {posLastTrains.map((lt: any) => {
                const remaining = (() => { const now = new Date(); const h = now.getHours(); const m = now.getMinutes(); const nowMin = (h < 5 ? h + 24 : h) * 60 + m; const [th, tm] = lt.arrive.split(':').map(Number); return (th < 5 ? th + 24 : th) * 60 + tm - nowMin })()
                const isPast = remaining < 0
                const isUrgent = remaining >= 0 && remaining <= 30
                return (
                  <span key={`${lt.from}-${lt.to}`} className="text-gray-400">
                    {lt.from}→{lt.to}
                    <span className={`ml-0.5 font-mono ${isPast ? 'text-gray-600' : isUrgent ? 'text-red-400 font-bold' : 'text-gray-300'}`}>{lt.arrive}着</span>
                    {isUrgent && <span className="text-red-400 ml-0.5">({remaining}分)</span>}
                    {isPast && <span className="text-gray-600 ml-0.5">終</span>}
                  </span>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {view === 'open' && tickets.map((ticket: any) => (
        <AutoExtender key={ticket.id} ticket={ticket} storeId={selectedStoreId} extensionPrice={extensionPrice} />
      ))}
      {view === 'open' && tickets.map((ticket: any) => (
        <JoinAutoExtender key={`join-${ticket.id}`} ticket={ticket} storeId={selectedStoreId} />
      ))}

      {view === 'open' ? (
        <CrossTicketTimerContext tickets={tickets}>
        {(castLatestMap) => (
        /* 伝票カード一覧：残り高さを全部使う */
        <div
          className="flex flex-col md:flex-row gap-3 overflow-y-auto md:overflow-x-auto flex-1 min-h-0 px-1 pb-1 md:items-start"
          onDragOver={e => {
            if (dragFromIdxRef.current !== null) {
              e.preventDefault()
              e.dataTransfer.dropEffect = 'move'
            }
          }}
          onDrop={e => {
            const fromIdx = dragFromIdxRef.current
            dragFromIdxRef.current = null
            if (fromIdx === null) return
            e.preventDefault()
            // ドロップ位置のカードを座標から判定
            const target = e.target as HTMLElement
            const card = target.closest('[data-ticket-idx]') as HTMLElement | null
            let toIdx = card ? parseInt(card.dataset.ticketIdx || '', 10) : tickets.length - 1
            if (isNaN(toIdx)) toIdx = tickets.length - 1
            if (fromIdx === toIdx) return
            const newOrder = [...tickets]
            const [moved] = newOrder.splice(fromIdx, 1)
            newOrder.splice(toIdx, 0, moved)
            const orderedIds = newOrder.map((t: any) => t.id)
            qc.setQueryData(['tickets', selectedStoreId, 'open'], newOrder)
            apiClient.post('/api/tickets/reorder', { store_id: selectedStoreId, ordered_ids: orderedIds })
              .then(() => qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId, 'open'] }))
          }}
        >
          {tickets.map((ticket: any, idx: number) => (
            <div key={ticket.id}
              data-ticket-idx={idx}
              draggable
              onDragStart={e => {
                const target = e.target as HTMLElement
                if (target.closest('[data-nopropagate]') || target.tagName === 'BUTTON') {
                  e.preventDefault()
                  return
                }
                dragFromIdxRef.current = idx
                e.dataTransfer.effectAllowed = 'move'
                try { e.dataTransfer.setData('text/plain', String(idx)) } catch {}
              }}
              onDragEnd={() => { dragFromIdxRef.current = null }}
              className="shrink-0"
            >
              <TicketCard ticket={ticket} storeId={selectedStoreId} onClick={() => setSelectedTicketId(ticket.id)}
                castLatestMap={castLatestMap}
                onOpenCustomerModal={t => setCustomerModalTicket(t)}
                onOpenCastModal={t => setCastModalTicket(t)}
                onOpenActiveCastsModal={t => setActiveCastsModalTicket(t)}
              />
            </div>
          ))}
          <div className="shrink-0 w-3" />
          {tickets.length === 0 && (
            <div className="flex-1 text-center text-gray-500 py-16">現在オープン中の伝票はありません</div>
          )}
        </div>
        )}
        </CrossTicketTimerContext>
      ) : view === 'casts' ? (
        <ActiveCastsView storeId={selectedStoreId} tickets={tickets} onTicketClick={(id) => setSelectedTicketId(id)} onOpenActiveCastsModal={t => setActiveCastsModalTicket(t)} />
      ) : view === 'attendance' ? (
        <CastAttendanceView storeId={selectedStoreId} />
      ) : view === 'history' ? (
        <ClosedTicketHistory storeId={selectedStoreId} onDetail={(id) => setSelectedTicketId(id)} />
      ) : view === 'logs' ? (
        <OrderLogsView storeId={selectedStoreId} />
      ) : (
        <SessionReportList storeId={selectedStoreId} />
      )}

      {/* カード上の顧客・キャスト選択モーダル（POSPage レベルで管理） */}
      {customerModalTicket && (
        <CustomerSearchModal
          storeId={selectedStoreId}
          currentId={customerModalTicket.customer_id}
          onSelect={id => {
            apiClient.post(`/api/tickets/${customerModalTicket.id}/set-customer`, { customer_id: id })
              .then(() => qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId, 'open'] }))
            setCustomerModalTicket(null)
          }}
          onClose={() => setCustomerModalTicket(null)}
        />
      )}
      {castModalTicket && (
        <CastAssignModal
          storeId={selectedStoreId}
          currentCastName={castModalTicket.featured_cast_name || null}
          onSelect={id => {
            apiClient.post(`/api/tickets/${castModalTicket.id}/set-cast`, { cast_id: id })
              .then(() => qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId, 'open'] }))
            setCastModalTicket(null)
          }}
          onClose={() => setCastModalTicket(null)}
        />
      )}
      {showTissueStartModal && (
        <TissueStartModal
          storeId={selectedStoreId}
          onClose={() => setShowTissueStartModal(false)}
          onStarted={() => {
            qc.invalidateQueries({ queryKey: ['tissue-active', selectedStoreId] })
            qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId, 'open'] })
            setShowTissueStartModal(false)
          }}
        />
      )}
      {showAIAdvisor && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setShowAIAdvisor(false)}>
          <div className="bg-night-900 border border-pink-500/30 rounded-xl max-w-3xl w-full max-h-[85vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
              <h3 className="text-white font-bold text-sm">🤖 付け回しAIアドバイス</h3>
              <div className="flex items-center gap-2">
                <div className="flex bg-gray-800 rounded p-0.5 gap-0.5">
                  <button onClick={() => setAIAdvisorTab('current')} className={`text-[10px] px-2 py-0.5 rounded ${aiAdvisorTab === 'current' ? 'bg-pink-700 text-white' : 'text-gray-400'}`}>最新</button>
                  <button onClick={async () => {
                    setAIAdvisorTab('history')
                    try { const r = await apiClient.get(`/api/ai/rotation-history/${selectedStoreId}`); setAIAdvisorHistory(r.data) } catch {}
                  }} className={`text-[10px] px-2 py-0.5 rounded ${aiAdvisorTab === 'history' ? 'bg-pink-700 text-white' : 'text-gray-400'}`}>履歴</button>
                </div>
                <button onClick={() => setShowAIAdvisor(false)} className="text-gray-400 hover:text-white text-xl leading-none">×</button>
              </div>
            </div>
            <div className="overflow-y-auto p-4 space-y-3">
              {aiAdvisorTab === 'current' ? (<>
              {aiAdvisorLoading && (
                <div className="text-center text-gray-400 py-8 text-sm">分析中... (Gemini 2.5 Flash)</div>
              )}
              {aiAdvisorError && (
                <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded p-3">{aiAdvisorError}</div>
              )}
              {aiAdvisorResult && (
                <>
                  {aiAdvisorResult.overall_advice && (
                    <div className="bg-pink-900/20 border border-pink-700/40 rounded-lg px-3 py-2 text-pink-200 text-xs">
                      💡 {aiAdvisorResult.overall_advice}
                    </div>
                  )}
                  {(aiAdvisorResult.suggestions || []).length === 0 && !aiAdvisorResult.overall_advice && (
                    <div className="text-gray-500 text-center py-6 text-xs">提案なし</div>
                  )}
                  {(aiAdvisorResult.suggestions || []).map((s: any) => (
                    <div key={s.ticket_id} className="bg-night-800 border border-gray-800 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-white font-bold text-sm">{s.table_no}</span>
                        <span className="text-gray-400 text-xs">{s.customer_name}</span>
                      </div>
                      <div className="space-y-1.5">
                        {(s.recommended_casts || []).map((c: any, i: number) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="text-pink-400 font-bold w-6 shrink-0">#{i + 1}</span>
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-white font-medium">{c.stage_name}</span>
                                <span className="text-[10px] text-gray-500">スコア {c.score}</span>
                              </div>
                              <div className="text-gray-400 text-[11px]">{c.reason}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </>
              )}
              </>) : (
                <>
                  {aiAdvisorHistory.length === 0 && <div className="text-gray-500 text-center py-6 text-xs">履歴なし</div>}
                  {aiAdvisorHistory.map((h: any) => (
                    <div key={h.id} className="bg-night-800 border border-gray-800 rounded-lg p-3">
                      <div className="text-[10px] text-gray-500 mb-2">{h.created_at ? new Date(h.created_at + 'Z').toLocaleString('ja-JP') : ''}</div>
                      {h.advice?.overall_advice && (
                        <div className="text-pink-200 text-xs mb-2">💡 {h.advice.overall_advice}</div>
                      )}
                      {(h.advice?.suggestions || []).map((s: any, si: number) => (
                        <div key={si} className="mb-1.5">
                          <span className="text-white text-xs font-bold">{s.table_no}</span>
                          <span className="text-gray-400 text-xs ml-1">{s.customer_name}</span>
                          <div className="ml-3">
                            {(s.recommended_casts || []).map((c: any, ci: number) => (
                              <div key={ci} className="text-[10px] text-gray-400">#{ci+1} {c.stage_name} ({c.score}) {c.reason}</div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
      )}
      {activeCastsModalTicket && (
        <ActiveCastsModal
          storeId={selectedStoreId}
          ticketId={activeCastsModalTicket.id}
          currentCastIds={(activeCastsModalTicket.current_casts || []).map((c: any) => c.cast_id).filter((x: any) => typeof x === 'number')}
          onSubmit={ids => {
            apiClient.post(`/api/tickets/${activeCastsModalTicket.id}/assignments/set`, { cast_ids: ids })
              .then(() => qc.invalidateQueries({ queryKey: ['tickets', selectedStoreId, 'open'] }))
            setActiveCastsModalTicket(null)
          }}
          onClose={() => setActiveCastsModalTicket(null)}
        />
      )}

      {showNewTicket && (
        <NewTicketModal
          storeId={selectedStoreId}
          onSubmit={({ tableNo, guestCount, planType, visitType, visitMotivation, motivationCastId, motivationNote }) =>
            createMutation.mutate({
              store_id: selectedStoreId,
              table_no: tableNo,
              guest_count: guestCount,
              plan_type: planType,
              visit_type: visitType,
              visit_motivation: visitMotivation,
              motivation_cast_id: motivationCastId,
              motivation_note: motivationNote,
            })
          }
          onClose={() => setShowNewTicket(false)}
        />
      )}

      {selectedTicketId && (
        <TicketDetailModal ticketId={selectedTicketId} storeId={selectedStoreId} onClose={() => setSelectedTicketId(null)} />
      )}

      {showOpenSessionModal && (
        <BusinessOpenModal
          onSubmit={(data) => openSessionMutation.mutate(data)}
          onClose={() => setShowOpenSessionModal(false)}
          isPending={openSessionMutation.isPending}
          lastClosedDiff={lastClosedSession?.cash_diff}
          lastClosingCashDetail={lastClosedSession?.closing_cash_detail}
        />
      )}

      {showCloseSessionModal && currentSession && (
        <BusinessCloseModal
          storeId={selectedStoreId}
          session={currentSession}
          openTicketCount={liveData?.open_count ?? 0}
          salesTotal={liveData?.closed_amount ?? 0}
          cashSales={liveData?.cash_sales ?? 0}
          cardTickets={liveData?.card_tickets ?? []}
          codeTickets={liveData?.code_tickets ?? []}
          expenses={closeModalExpenses}
          onExpensesChange={setCloseModalExpenses}
          withdrawals={closeModalWithdrawals}
          onWithdrawalsChange={setCloseModalWithdrawals}
          notes={closeModalNotes}
          onNotesChange={setCloseModalNotes}
          onSubmit={(closing_cash, closing_cash_detail, notes, cash_diff, expenses_detail, cash_sales, card_sales, code_sales) => closeSessionMutation.mutate({ closing_cash, closing_cash_detail, notes, cash_diff, expenses_detail, cash_sales, card_sales, code_sales })}
          onClose={() => setShowCloseSessionModal(false)}
          isPending={closeSessionMutation.isPending}
        />
      )}

      {/* 営業終了後 お疲れさまでした */}
      {showSessionThanks && (
        <div className="fixed inset-0 z-[90] bg-gray-950 flex flex-col items-center justify-center gap-6 animate-fade-in">
          <div className="text-6xl">🌙</div>
          <div className="text-3xl font-black text-white tracking-wide">本日もお疲れさまでした</div>
          <div className="text-gray-400 text-sm">営業お疲れ様でした。またお会いしましょう。</div>
          <button onClick={() => setShowSessionThanks(false)} className="mt-4 text-gray-600 text-xs hover:text-gray-400">閉じる</button>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────
// 金種テーブル＋テンキー（共通）
// ─────────────────────────────────────────
const DENOMS = [10000, 5000, 2000, 1000, 500, 100, 50, 10, 5, 1]

function CashDenomPad({ counts, onChange, extraAmount = 0 }: {
  counts: Record<number, number>
  onChange: (denom: number, count: number) => void
  extraAmount?: number
}) {
  const [selectedDenom, setSelectedDenom] = useState<number>(10000)
  const [inputBuf, setInputBuf] = useState('')

  const handlePad = (key: string) => {
    if (key === 'C') {
      setInputBuf('')
      onChange(selectedDenom, 0)
      return
    }
    if (key === 'OK') {
      const v = parseInt(inputBuf, 10) || 0
      onChange(selectedDenom, v)
      setInputBuf('')
      // 次の金種へ
      const idx = DENOMS.indexOf(selectedDenom)
      if (idx < DENOMS.length - 1) setSelectedDenom(DENOMS[idx + 1])
      return
    }
    const next = inputBuf + key
    if (next.length > 5) return
    setInputBuf(next)
    onChange(selectedDenom, parseInt(next, 10) || 0)
  }

  const handleSelectRow = (d: number) => {
    setSelectedDenom(d)
    setInputBuf(counts[d] > 0 ? String(counts[d]) : '')
  }

  const total = DENOMS.reduce((s, d) => s + d * (counts[d] || 0), 0)

  const PAD_KEYS = [['7','8','9','C'],['4','5','6',''],['1','2','3','OK'],['0','00','','']]

  return (
    <div className="flex gap-3">
      {/* 金種テーブル */}
      <div className="flex-1 min-w-0">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-700">
              <th className="px-2 py-1 text-left text-gray-300 font-medium border border-gray-600">金種</th>
              <th className="px-2 py-1 text-right text-gray-300 font-medium border border-gray-600">枚数</th>
              <th className="px-2 py-1 text-right text-gray-300 font-medium border border-gray-600">金額</th>
            </tr>
          </thead>
          <tbody>
            {DENOMS.map(d => {
              const cnt = counts[d] || 0
              const isSelected = d === selectedDenom
              return (
                <tr key={d}
                  onClick={() => handleSelectRow(d)}
                  className={`cursor-pointer border border-gray-600 transition-colors ${isSelected ? 'bg-yellow-900/60' : cnt > 0 ? 'bg-gray-800' : 'bg-gray-900 hover:bg-gray-800'}`}>
                  <td className={`px-2 py-1 text-right font-medium ${isSelected ? 'text-yellow-300' : 'text-gray-300'}`}>
                    {d.toLocaleString()}
                  </td>
                  <td className={`px-2 py-1 text-right ${cnt > 0 ? 'text-white' : 'text-gray-600'}`}>
                    {isSelected && inputBuf ? inputBuf : (cnt > 0 ? cnt : 0)}
                  </td>
                  <td className={`px-2 py-1 text-right ${cnt > 0 ? 'text-white' : 'text-gray-600'}`}>
                    {(d * cnt).toLocaleString()}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* テンキー */}
      <div className="shrink-0 w-32 space-y-1.5">
        {PAD_KEYS.map((row, ri) => (
          <div key={ri} className="grid grid-cols-4 gap-1">
            {row.map((k, ki) => {
              if (!k) return <div key={ki} />
              const isC = k === 'C'
              const isOK = k === 'OK'
              return (
                <button key={ki}
                  onClick={() => handlePad(k)}
                  className={`${isOK ? 'col-span-1 row-span-2' : ''} ${isC ? 'text-red-400 bg-gray-700 hover:bg-gray-600' : isOK ? 'bg-green-700 hover:bg-green-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-white'} rounded text-sm font-bold h-8 transition-colors active:scale-95`}>
                  {k}
                </button>
              )
            })}
          </div>
        ))}
        {/* 合計 */}
        <div className="mt-2 border-t border-gray-600 pt-2 text-center">
          <div className="text-xs text-gray-400">準備金合計</div>
          <div className="text-green-400 font-bold text-sm">¥{(total + extraAmount).toLocaleString()}</div>
          {extraAmount !== 0 && (
            <div className={`text-[10px] mt-0.5 ${extraAmount > 0 ? 'text-green-600' : 'text-red-500'}`}>
              金種計 ¥{total.toLocaleString()} {extraAmount > 0 ? '+' : ''}¥{extraAmount.toLocaleString()}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────
// 営業開始モーダル
// ─────────────────────────────────────────
function BusinessOpenModal({ onSubmit, onClose, isPending, lastClosedDiff, lastClosingCashDetail }: {
  onSubmit: (data: { opening_cash: number; opening_cash_detail: Record<string, number>; prev_day_diff: number; operator_name?: string; event_name?: string; notes?: string }) => void
  onClose: () => void
  isPending: boolean
  lastClosedDiff?: number | null
  lastClosingCashDetail?: Record<string, number> | null
}) {
  const [counts, setCounts] = useState<Record<number, number>>({})
  const initializedRef = useRef(false)
  useEffect(() => {
    if (lastClosingCashDetail && !initializedRef.current) {
      initializedRef.current = true
      const result: Record<number, number> = {}
      for (const [k, v] of Object.entries(lastClosingCashDetail)) {
        result[Number(k)] = v
      }
      setCounts(result)
    }
  }, [lastClosingCashDetail])
  const [prevDayDiff, setPrevDayDiff] = useState('')
  const [prevDaySign, setPrevDaySign] = useState<'+' | '-'>('+')
  const [operatorName, setOperatorName] = useState('')
  const [eventName, setEventName] = useState('')
  const [notes, setNotes] = useState('')

  // 前回終了時の過不足金を自動反映
  useEffect(() => {
    if (lastClosedDiff != null && lastClosedDiff !== 0) {
      setPrevDaySign(lastClosedDiff < 0 ? '-' : '+')
      setPrevDayDiff(String(Math.abs(lastClosedDiff)))
    }
  }, [lastClosedDiff])

  const total = DENOMS.reduce((s, d) => s + d * (counts[d] || 0), 0)
  const diffAbs = parseInt(prevDayDiff.replace(/,/g, ''), 10) || 0
  const diff = prevDaySign === '-' ? -diffAbs : diffAbs

  const handleChange = (denom: number, count: number) => {
    setCounts(prev => ({ ...prev, [denom]: count }))
  }

  const handleSubmit = () => {
    const detail: Record<string, number> = {}
    DENOMS.forEach(d => { if (counts[d] > 0) detail[String(d)] = counts[d] })
    onSubmit({
      opening_cash: total,
      opening_cash_detail: detail,
      prev_day_diff: diff,
      operator_name: operatorName || undefined,
      event_name: eventName || undefined,
      notes: notes || undefined,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-2 sm:p-4 overflow-y-auto">
      <div className="card w-full max-w-2xl space-y-4 my-auto">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white text-lg">営業開始</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        {/* 金種テーブル＋テンキー */}
        <CashDenomPad counts={counts} onChange={handleChange} extraAmount={diff} />

        {/* その他入力 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">前日過不足金</label>
            <div className="flex gap-1">
              <div className="flex rounded-xl overflow-hidden border border-gray-700 shrink-0">
                <button
                  onClick={() => setPrevDaySign('+')}
                  className={`px-3 py-2 text-sm font-bold transition-colors ${prevDaySign === '+' ? 'bg-green-700 text-white' : 'bg-gray-800 text-gray-500 hover:text-gray-300'}`}>
                  ＋
                </button>
                <button
                  onClick={() => setPrevDaySign('-')}
                  className={`px-3 py-2 text-sm font-bold transition-colors ${prevDaySign === '-' ? 'bg-red-700 text-white' : 'bg-gray-800 text-gray-500 hover:text-gray-300'}`}>
                  －
                </button>
              </div>
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">¥</span>
                <input
                  type="number"
                  value={prevDayDiff}
                  onChange={e => setPrevDayDiff(e.target.value)}
                  className="input-field w-full pl-7"
                  placeholder="0"
                  min={0}
                />
              </div>
            </div>
            {diffAbs > 0 && (
              <p className={`text-xs mt-1 ${prevDaySign === '+' ? 'text-green-400' : 'text-red-400'}`}>
                {prevDaySign === '+' ? '過剰' : '不足'} ¥{diffAbs.toLocaleString()}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">担当者名（任意）</label>
            <input type="text" value={operatorName} onChange={e => setOperatorName(e.target.value)}
              className="input-field w-full" placeholder="担当者" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">本日企画名（任意）</label>
            <input type="text" value={eventName} onChange={e => setEventName(e.target.value)}
              className="input-field w-full" placeholder="例: バースデーイベント" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">メモ（任意）</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              className="input-field w-full" placeholder="引き継ぎ事項など" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button onClick={onClose} className="btn-secondary">キャンセル</button>
          <button onClick={handleSubmit} disabled={isPending}
            className="bg-green-700 hover:bg-green-600 text-white font-medium px-4 py-2.5 rounded-xl transition-colors disabled:opacity-50">
            営業開始
          </button>
        </div>
      </div>
    </div>
  )
}

// 終了モーダル専用テンキー（selectedDenomを外から制御）
function CloseModalDenomPad({ counts, onChange, extraAmount = 0, selectedDenom, onSelectDenom, carryover, onCarryoverChange, openingCash, cashSales, onInputBuf, diff = 0 }: {
  counts: Record<number, number>
  onChange: (denom: number, count: number) => void
  extraAmount?: number
  selectedDenom: number
  onSelectDenom: (d: number) => void
  carryover: number
  onCarryoverChange: (v: number) => void
  openingCash: number
  cashSales: number
  onInputBuf?: (buf: string) => void
  diff?: number
}) {
  const [inputBuf, setInputBuf] = useState('')
  const total = DENOMS.reduce((s, d) => s + d * (counts[d] || 0), 0)

  const setBuf = (v: string) => { setInputBuf(v); onInputBuf?.(v) }

  const handlePad = (key: string) => {
    if (key === 'C') { setBuf(''); onChange(selectedDenom, 0); return }
    if (key === 'OK') {
      const v = parseInt(inputBuf, 10) || 0
      onChange(selectedDenom, v)
      setBuf('')
      const idx = DENOMS.indexOf(selectedDenom)
      if (idx < DENOMS.length - 1) onSelectDenom(DENOMS[idx + 1])
      return
    }
    const next = inputBuf + key
    if (next.length > 5) return
    setBuf(next)
  }

  const PAD_KEYS = [['7','8','9','C'],['4','5','6',''],['1','2','3','OK'],['0','00','','']]

  return (
    <div className="shrink-0 flex flex-col gap-1.5 w-52">
      {PAD_KEYS.map((row, ri) => (
        <div key={ri} className="grid grid-cols-4 gap-1.5">
          {row.map((k, ki) => {
            if (!k) return <div key={ki} />
            const isC = k === 'C', isOK = k === 'OK'
            return (
              <button key={ki} onClick={() => handlePad(k)}
                className={`${isC ? 'text-red-400 bg-gray-700 hover:bg-gray-600' : isOK ? 'bg-green-700 hover:bg-green-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-white'} rounded text-base font-bold h-11 transition-colors active:scale-95`}>
                {k}
              </button>
            )
          })}
        </div>
      ))}
      <div className="border-t border-gray-600 pt-1.5 mt-1 space-y-1.5">
        {/* 繰越金入力 */}
        <div>
          <div className="text-[10px] text-gray-400 mb-0.5">繰越金（差し引き）</div>
          <div className="relative">
            <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">¥</span>
            <input
              type="number" min={0} placeholder="0"
              value={carryover || ''}
              onChange={e => onCarryoverChange(parseInt(e.target.value, 10) || 0)}
              className="input-field w-full pl-6 text-xs py-1"
            />
          </div>
        </div>
        {/* 準備金合計 = 開始レジ金 + レジ内現金合計 + extraAmount - 繰越金 */}
        <div className="flex items-start justify-between gap-1 mt-0.5">
          <div>
            <div className="text-[10px] text-gray-400">準備金合計</div>
            <div className={`font-bold text-sm ${(openingCash + cashSales + extraAmount - carryover) < 0 ? 'text-red-400' : 'text-green-400'}`}>
              ¥{(openingCash + cashSales + extraAmount - carryover).toLocaleString()}
            </div>
            <div className="text-[9px] text-gray-500">
              開始¥{openingCash.toLocaleString()}+現金¥{cashSales.toLocaleString()}
              {extraAmount !== 0 && <span className="text-red-500"> -¥{Math.abs(extraAmount).toLocaleString()}</span>}
              {carryover > 0 && <span className="text-orange-500"> -¥{carryover.toLocaleString()}</span>}
            </div>
            {inputBuf && (
              <div className="text-yellow-400 text-xs">{inputBuf} 枚</div>
            )}
          </div>
          {diff !== 0 && (
            <div className="text-right shrink-0">
              <div className="text-[10px] text-gray-400">過不足金</div>
              <div className={`font-bold text-sm ${diff > 0 ? 'text-blue-300' : 'text-red-400'}`}>
                {diff > 0 ? '+' : ''}¥{diff.toLocaleString()}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────
// 営業終了モーダル
// ─────────────────────────────────────────
const LIQUOR_CATEGORIES = ['田野屋', 'カクヤス', 'その他酒類'] as const

interface ExpenseRow {
  id: number
  type: 'liquor' | 'other'
  category: string   // 酒類: 田野屋/カクヤス/その他酒類, その他: 自由テキスト
  amount: string
}

function WithdrawalRow({ w, storeId, onUpdate, onRemove }: {
  w: { id: number; type: string; name: string; amount: string }
  storeId: number
  onUpdate: (field: 'type' | 'name' | 'amount', value: string) => void
  onRemove: () => void
}) {
  const [q, setQ] = useState(w.name)
  const [open, setOpen] = useState(false)
  const prevIdRef = useRef(w.id)
  if (prevIdRef.current !== w.id) {
    prevIdRef.current = w.id
    if (q !== w.name) setQ(w.name)
  }

  const isDailyPay = w.type === '日払い' || w.type === 'ヘルプ日払い'

  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
    enabled: isDailyPay && !!storeId,
  })
  const { data: attendance = [] } = useQuery({
    queryKey: ['attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/attendance/working/${storeId}`).then(r => r.data),
    enabled: isDailyPay && !!storeId,
  })
  const { data: staffAttendance = [] } = useQuery({
    queryKey: ['staff-attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/staff-attendance/today/${storeId}`).then(r => r.data),
    enabled: isDailyPay && !!storeId,
  })
  // 退勤済み（actual_end あり）のキャストIDセット
  const clockedOutIds = new Set((attendance as any[]).filter((a: any) => !!a.actual_end).map((a: any) => a.cast_id))
  const filteredCasts = (castsAll as any[]).filter((c: any) =>
    c.is_active && clockedOutIds.has(c.id) && (!q || c.stage_name?.includes(q))
  )
  // 社員/アルバイト（本日出勤記録あり・名前フィルタ）
  const filteredStaff = (staffAttendance as any[]).filter((s: any) =>
    !q || s.name?.includes(q)
  )
  const hasDropdown = filteredCasts.length > 0 || filteredStaff.length > 0

  const handleSelect = (name: string) => {
    setQ(name)
    onUpdate('name', name)
    setOpen(false)
  }

  // isDailyPayでなくなったとき（種別変更）は通常テキスト入力に戻す
  if (!isDailyPay) {
    return (
      <div className="flex gap-1.5 items-center">
        <select value={w.type} onChange={ev => { onUpdate('type', ev.target.value); setQ(''); onUpdate('name', '') }}
          className="input-field text-xs py-2 w-32 shrink-0">
          <option value="">選択...</option>
          <option value="日払い">日払い</option>
          <option value="ヘルプ日払い">ヘルプ日払い</option>
          <option value="その他">その他</option>
        </select>
        <input type="text" placeholder="備考（任意）" value={q}
          onChange={ev => { setQ(ev.target.value) }}
          onBlur={() => onUpdate('name', q)}
          className="input-field text-xs flex-1 py-2" />
        <div className="relative w-28 shrink-0">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">¥</span>
          <input type="number" min={0} placeholder="0" value={w.amount}
            onChange={ev => onUpdate('amount', ev.target.value)}
            className="input-field w-full pl-6 text-xs py-2" />
        </div>
        <button onClick={onRemove} className="text-gray-600 hover:text-red-400 shrink-0"><X className="w-3.5 h-3.5" /></button>
      </div>
    )
  }

  return (
    <div className="flex gap-1.5 items-start">
      <select value={w.type} onChange={ev => { onUpdate('type', ev.target.value); setQ(''); onUpdate('name', '') }}
        className="input-field text-xs py-2 w-32 shrink-0">
        <option value="">選択...</option>
        <option value="日払い">日払い</option>
        <option value="ヘルプ日払い">ヘルプ日払い</option>
        <option value="その他">その他</option>
      </select>
      <div className="flex-1 relative">
        <input type="text" placeholder="キャスト名または社員名で検索" value={q}
          onChange={ev => { setQ(ev.target.value); setOpen(true); onUpdate('name', ev.target.value) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          className="input-field text-xs w-full py-2" />
        {open && hasDropdown && (
          <div className="absolute top-full left-0 right-0 z-50 bg-gray-800 border border-gray-600 rounded-lg mt-0.5 max-h-48 overflow-y-auto shadow-xl">
            {filteredCasts.length > 0 && (
              <>
                <div className="px-3 py-1 text-xs text-gray-500 bg-gray-900/60 font-medium">キャスト</div>
                {filteredCasts.map((c: any) => (
                  <button key={c.id} onMouseDown={() => handleSelect(c.stage_name)}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-700 transition-colors">
                    {c.stage_name}
                  </button>
                ))}
              </>
            )}
            {filteredStaff.length > 0 && (
              <>
                <div className="px-3 py-1 text-xs text-gray-500 bg-gray-900/60 font-medium">社員/アルバイト</div>
                {filteredStaff.map((s: any) => (
                  <button key={s.id} onMouseDown={() => handleSelect(s.name)}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-700 transition-colors">
                    {s.name}
                    {s.is_absent && <span className="text-red-400 ml-1.5 text-xs">当欠</span>}
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
      <div className="relative w-28 shrink-0">
        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">¥</span>
        <input type="number" min={0} placeholder="0" value={w.amount}
          onChange={ev => onUpdate('amount', ev.target.value)}
          className="input-field w-full pl-6 text-xs py-2" />
      </div>
      <button onClick={onRemove} className="text-gray-600 hover:text-red-400 shrink-0 mt-2"><X className="w-3.5 h-3.5" /></button>
    </div>
  )
}

function BusinessCloseModal({ storeId, session, openTicketCount, salesTotal, cashSales, cardTickets, codeTickets, expenses, onExpensesChange, withdrawals, onWithdrawalsChange, notes, onNotesChange, onSubmit, onClose, isPending }: {
  storeId: number
  session: any
  openTicketCount: number
  salesTotal: number
  cashSales: number
  cardTickets: any[]
  codeTickets: any[]
  expenses: ExpenseRow[]
  onExpensesChange: React.Dispatch<React.SetStateAction<ExpenseRow[]>>
  withdrawals: { id: number; type: string; name: string; amount: string }[]
  onWithdrawalsChange: React.Dispatch<React.SetStateAction<{ id: number; type: string; name: string; amount: string }[]>>
  notes: string
  onNotesChange: (v: string) => void
  onSubmit: (closing_cash: number, closing_cash_detail: Record<string, number>, notes?: string, cash_diff?: number | null, expenses_detail?: any, cash_sales?: number, card_sales?: number, code_sales?: number) => void
  onClose: () => void
  isPending: boolean
}) {
  const [counts, setCounts] = useState<Record<number, number>>({})
  const [selectedDenom, setSelectedDenom] = useState<number>(10000)
  const [inputBuf, setInputBuf] = useState('')
  const [carryover, setCarryover] = useState(0)
  const [showPaymentModal, setShowPaymentModal] = useState<'card' | 'code' | null>(null)
  const [showCarryoverConfirm, setShowCarryoverConfirm] = useState(false)
  const [operatorName, setOperatorName] = useState('')
  const setExpenses = onExpensesChange
  const setWithdrawals = onWithdrawalsChange
  const setNotes = onNotesChange
  // 既存の id より大きい値から始めることで、モーダル再オープン時の id 衝突を防ぐ
  const maxExistingId = Math.max(
    0,
    ...expenses.map(e => e.id),
    ...withdrawals.map(w => w.id),
  )
  const nextId = useRef(Math.max(1000, maxExistingId))

  const total = DENOMS.reduce((s, d) => s + d * (counts[d] || 0), 0)
  const openedTime = session.opened_at ? new Date(session.opened_at + (session.opened_at.endsWith('Z') ? '' : 'Z')) : null

  // その他経費＋出金名目を差し引く
  const otherExpenseTotal = expenses
    .filter(e => e.type === 'other')
    .reduce((s, e) => s + (parseInt(e.amount, 10) || 0), 0)
  const withdrawalTotal = withdrawals.reduce((s, w) => s + (parseInt(w.amount, 10) || 0), 0)
  const deductTotal = otherExpenseTotal + withdrawalTotal
  // 準備金合計 = 開始レジ金 + レジ内現金合計(cashSales) - 経費出金 - 繰越金
  const expectedCash = (session.opening_cash || 0) + cashSales - deductTotal - carryover
  const diff = total - expectedCash  // 金種合計 vs 準備金合計

  const updateWithdrawal = (id: number, field: 'type' | 'name' | 'amount', value: string) => {
    setWithdrawals(prev => prev.map(w => w.id === id ? { ...w, [field]: value } : w))
  }

  const addWithdrawal = () => {
    nextId.current++
    setWithdrawals(prev => [...prev, { id: nextId.current, type: '', name: '', amount: '' }])
  }

  const removeWithdrawal = (id: number) => setWithdrawals(prev => prev.filter(w => w.id !== id))

  const updateExpense = (id: number, field: 'category' | 'amount', value: string) => {
    setExpenses(prev => {
      const updated = prev.map(e => e.id === id ? { ...e, [field]: value } : e)
      // その他経費: 最後の行に何か入力されたら新しい空行を追加
      const lastOther = [...updated].reverse().find(e => e.type === 'other')
      if (lastOther && (lastOther.category || lastOther.amount)) {
        const allOthers = updated.filter(e => e.type === 'other')
        const last = allOthers[allOthers.length - 1]
        if (last.category || last.amount) {
          nextId.current++
          return [...updated, { id: nextId.current, type: 'other', category: '', amount: '' }]
        }
      }
      return updated
    })
  }

  const updateLiquorExpense = (id: number, field: 'category' | 'amount', value: string) => {
    setExpenses(prev => {
      const updated = prev.map(e => e.id === id ? { ...e, [field]: value } : e)
      // 酒類経費: 最後の行に何か入力されたら新しい空行を追加
      const allLiquors = updated.filter(e => e.type === 'liquor')
      const last = allLiquors[allLiquors.length - 1]
      if (last.amount) {
        nextId.current++
        return [...updated, { id: nextId.current, type: 'liquor', category: '田野屋', amount: '' }]
      }
      return updated
    })
  }

  const removeExpense = (id: number) => {
    setExpenses(prev => prev.filter(e => e.id !== id))
  }

  const doSubmit = (cashDiff: number | null) => {
    const detail: Record<string, number> = {}
    DENOMS.forEach(d => { if (counts[d] > 0) detail[String(d)] = counts[d] })
    // 経費・出金をまとめてJSON化
    const expensesPayload = {
      liquor: expenses.filter(e => e.type === 'liquor' && e.amount).map(e => ({ category: e.category, amount: parseInt(e.amount, 10) || 0 })),
      other: expenses.filter(e => e.type === 'other' && (e.category || e.amount)).map(e => ({ category: e.category, amount: parseInt(e.amount, 10) || 0 })),
      withdrawals: withdrawals
        .filter(w => w.amount && w.type)
        .map(w => ({
          type: w.type,
          person_name: w.name || '',
          name: w.name ? `${w.type}（${w.name}）` : w.type,
          amount: parseInt(w.amount, 10) || 0,
        })),
    }
    onSubmit(total, detail, notes || undefined, cashDiff, expensesPayload, cashSales, cardSales, codeSales)
  }

  // 決済別内訳（各チケットの実際の決済金額フィールドで集計）
  const cardSales = cardTickets.reduce((s: number, t: any) => s + (t.card_amount || t.grand_total || 0), 0)
  const codeSales = codeTickets.reduce((s: number, t: any) => s + (t.code_amount || t.grand_total || 0), 0)

  const [showOpenTicketBlock, setShowOpenTicketBlock] = useState(false)

  const handleSubmit = () => {
    if (openTicketCount > 0) {
      setShowOpenTicketBlock(true)
      return
    }
    if (diff !== 0) {
      setShowCarryoverConfirm(true)
      return
    }
    doSubmit(null)
  }

  const liquorExpenses = expenses.filter(e => e.type === 'liquor')
  const otherExpenses = expenses.filter(e => e.type === 'other')

  return (
    <div className="fixed inset-0 bg-gray-950 z-50 flex flex-col">
      {/* ヘッダー＋サマリー（1行） */}
      <div className="shrink-0 flex items-center gap-4 px-4 py-2 border-b border-gray-800 bg-gray-900/60">
        <h3 className="font-bold text-white text-base shrink-0">営業日報</h3>
        <div className="flex items-center gap-4 text-xs flex-1 min-w-0">
          <span className="text-gray-500 shrink-0">
            開始 <span className="text-white font-medium">
              {openedTime ? `${toBarHour(openedTime.getHours()).toString().padStart(2,'0')}:${openedTime.getMinutes().toString().padStart(2,'0')}` : '—'}
            </span>
          </span>
          <span className="text-gray-500 shrink-0">開始レジ金 <span className="text-white font-medium">¥{(session.opening_cash || 0).toLocaleString()}</span></span>
          <span className="text-gray-500 shrink-0">本日売上 <span className="text-green-400 font-bold">¥{salesTotal.toLocaleString()}</span></span>
          <span className="text-gray-500 shrink-0">レジ内現金合計 <span className="text-yellow-400 font-bold">¥{cashSales.toLocaleString()}</span></span>
          {openTicketCount > 0 && (
            <span className="text-red-400 font-bold shrink-0">⚠ 未会計 {openTicketCount} 卓</span>
          )}
        </div>
        <button onClick={onClose} className="shrink-0 text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1 rounded-lg transition-colors">戻る</button>
      </div>

      {/* メインコンテンツ 2カラム */}
      <div className="flex-1 min-h-0 flex">
        {/* 左：金種テーブル */}
        <div className="w-1/2 border-r border-gray-800 flex flex-col px-3 pt-2 pb-2 gap-1.5">
          <div className="shrink-0">
            <label className="text-xs text-gray-400 mb-0.5 block">担当者名</label>
            <input type="text" value={operatorName} onChange={e => setOperatorName(e.target.value)}
              className="input-field w-full text-sm py-1.5" placeholder="担当者" />
          </div>
          <div className="text-xs text-gray-400 font-medium shrink-0">終了レジ金（金種別入力）</div>
          <div className="flex-1 min-h-0 flex gap-2">
            {/* 金種テーブル */}
            <div className="flex-1 min-w-0">
              <table className="w-full text-xs border-collapse h-full table-fixed">
                <colgroup>
                  <col style={{width:'72px'}} />
                  <col style={{width:'44px'}} />
                  <col style={{width:'110px'}} />
                </colgroup>
                <thead>
                  <tr className="bg-gray-700">
                    <th className="px-1 py-0.5 text-right text-gray-300 font-medium border border-gray-600">金種</th>
                    <th className="px-1 py-0.5 text-right text-gray-300 font-medium border border-gray-600">枚数</th>
                    <th className="px-1 py-0.5 text-right text-gray-300 font-medium border border-gray-600">金額</th>
                  </tr>
                </thead>
                <tbody>
                  {DENOMS.map(d => {
                    const cnt = counts[d] || 0
                    const isSel = d === selectedDenom
                    return (
                      <tr key={d} onClick={() => setSelectedDenom(d)}
                        className={`border border-gray-600 cursor-pointer transition-colors ${isSel ? 'bg-yellow-900/50' : cnt > 0 ? 'bg-gray-800' : 'bg-gray-900 hover:bg-gray-800'}`}>
                        <td className={`px-1 py-0.5 text-right font-medium leading-5 ${isSel ? 'text-yellow-300' : 'text-gray-300'}`}>{d.toLocaleString()}</td>
                        <td className="px-1 py-0.5 text-center leading-5">
                          {isSel && inputBuf
                            ? <span className="text-yellow-400 font-bold">{inputBuf}</span>
                            : cnt > 0 ? <span className="text-white">{cnt}</span> : <span className="text-gray-700">0</span>}
                        </td>
                        <td className="px-1 py-0.5 text-right text-white leading-5">{cnt > 0 ? (d * cnt).toLocaleString() : <span className="text-gray-700">0</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* テンキー */}
            <CloseModalDenomPad
              counts={counts}
              onChange={(d, v) => setCounts(prev => ({ ...prev, [d]: v }))}
              extraAmount={-deductTotal}
              selectedDenom={selectedDenom}
              onSelectDenom={setSelectedDenom}
              carryover={carryover}
              onCarryoverChange={setCarryover}
              openingCash={session.opening_cash || 0}
              cashSales={cashSales}
              onInputBuf={setInputBuf}
              diff={diff}
            />
          </div>
          {diff === 0 && (
            <div className="shrink-0 flex items-center gap-2 py-1">
              <span className="text-2xl font-black text-yellow-400 tracking-widest drop-shadow-[0_0_8px_rgba(250,204,21,0.8)]">PERFECT!</span>
              <span className="text-xs text-green-400">準備金合計との差: ±¥0</span>
            </div>
          )}

          {/* カード/コード会計ボタン */}
          {(cardTickets.length > 0 || codeTickets.length > 0) && (
            <div className="shrink-0 border-t border-gray-800 pt-1.5 flex gap-2">
              {cardTickets.length > 0 && (
                <button onClick={() => setShowPaymentModal('card')}
                  className="flex-1 bg-blue-900/30 hover:bg-blue-900/50 border border-blue-700/50 rounded-lg px-2 py-1.5 text-left transition-colors">
                  <div className="text-xs text-blue-400 font-medium">カード会計 {cardTickets.length}件</div>
                  <div className="text-blue-300 font-bold text-xs">¥{cardTickets.reduce((s: number, t: any) => s + (t.card_amount || 0), 0).toLocaleString()}</div>
                </button>
              )}
              {codeTickets.length > 0 && (
                <button onClick={() => setShowPaymentModal('code')}
                  className="flex-1 bg-purple-900/30 hover:bg-purple-900/50 border border-purple-700/50 rounded-lg px-2 py-1.5 text-left transition-colors">
                  <div className="text-xs text-purple-400 font-medium">コード決済 {codeTickets.length}件</div>
                  <div className="text-purple-300 font-bold text-xs">¥{codeTickets.reduce((s: number, t: any) => s + (t.code_amount || 0), 0).toLocaleString()}</div>
                </button>
              )}
            </div>
          )}
        </div>

        {/* 右：経費・出金・その他 */}
        <div className="w-1/2 flex flex-col overflow-y-auto p-3 gap-3">
          {/* 酒類経費 */}
          <div>
            <div className="text-xs text-gray-400 mb-1.5 font-medium">酒類経費</div>
            <div className="space-y-1.5">
              {liquorExpenses.map((e, i) => (
                <div key={e.id} className="flex gap-1.5 items-center">
                  <select value={e.category} onChange={ev => updateLiquorExpense(e.id, 'category', ev.target.value)}
                    className="input-field text-xs flex-1 py-2">
                    {LIQUOR_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <div className="relative w-28 shrink-0">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">¥</span>
                    <input type="number" min={0} placeholder="0" value={e.amount}
                      onChange={ev => updateLiquorExpense(e.id, 'amount', ev.target.value)}
                      className="input-field w-full pl-6 text-xs py-2" />
                  </div>
                  {liquorExpenses.length > 1 && i < liquorExpenses.length - 1 && (
                    <button onClick={() => removeExpense(e.id)} className="text-gray-600 hover:text-red-400 shrink-0"><X className="w-3.5 h-3.5" /></button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* その他経費 */}
          <div>
            <div className="text-xs text-gray-400 mb-1.5 font-medium">その他経費 <span className="text-orange-400">（差し引き）</span></div>
            <div className="space-y-1.5">
              {otherExpenses.map((e, i) => (
                <div key={e.id} className="flex gap-1.5 items-center">
                  <input type="text" placeholder="経費内容" value={e.category}
                    onChange={ev => updateExpense(e.id, 'category', ev.target.value)}
                    className="input-field text-xs flex-1 py-2" />
                  <div className="relative w-28 shrink-0">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">¥</span>
                    <input type="number" min={0} placeholder="0" value={e.amount}
                      onChange={ev => updateExpense(e.id, 'amount', ev.target.value)}
                      className="input-field w-full pl-6 text-xs py-2" />
                  </div>
                  {otherExpenses.length > 1 && i < otherExpenses.length - 1 && (
                    <button onClick={() => removeExpense(e.id)} className="text-gray-600 hover:text-red-400 shrink-0"><X className="w-3.5 h-3.5" /></button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 出金名目 */}
          <div>
            <div className="text-xs text-gray-400 mb-1.5 font-medium">出金名目 <span className="text-orange-400">（差し引き）</span></div>
            <div className="space-y-1.5">
              {withdrawals.map((w) => (
                <WithdrawalRow
                  key={w.id}
                  w={w}
                  storeId={storeId}
                  onUpdate={(field, value) => updateWithdrawal(w.id, field, value)}
                  onRemove={() => removeWithdrawal(w.id)}
                />
              ))}
              <button onClick={addWithdrawal} className="text-xs text-gray-400 hover:text-white mt-1">＋ 追加</button>
            </div>
          </div>

          {/* メモ */}
          <div>
            <label className="text-xs text-gray-400 mb-1 block">メモ（任意）</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              className="input-field w-full text-sm" placeholder="引き継ぎ事項など" />
          </div>
        </div>
      </div>

      {/* カード/コード会計詳細モーダル */}
      {showPaymentModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4">
          <div className="card w-full max-w-md max-h-[80vh] flex flex-col">
            <div className="flex justify-between items-center mb-3 shrink-0">
              <h4 className="font-bold text-white">
                {showPaymentModal === 'card' ? 'カード会計' : 'コード決済'}一覧
              </h4>
              <button onClick={() => setShowPaymentModal(null)}><X className="w-5 h-5 text-gray-400" /></button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-1">
              {(showPaymentModal === 'card' ? cardTickets : codeTickets).map((t: any) => {
                const amt = showPaymentModal === 'card' ? (t.card_amount || 0) : (t.code_amount || 0)
                const endedAt = t.ended_at ? new Date(t.ended_at.endsWith('Z') ? t.ended_at : t.ended_at + 'Z') : null
                return (
                  <div key={t.id} className="flex justify-between items-center bg-gray-800 rounded-lg px-3 py-2">
                    <div>
                      <span className="font-bold text-white text-sm">{t.table_no || '—'}</span>
                      {endedAt && (
                        <span className="text-gray-500 text-xs ml-2">
                          {toBarHour(endedAt.getHours()).toString().padStart(2,'0')}:{endedAt.getMinutes().toString().padStart(2,'0')}
                        </span>
                      )}
                    </div>
                    <span className={`font-bold text-sm ${showPaymentModal === 'card' ? 'text-blue-400' : 'text-purple-400'}`}>
                      ¥{amt.toLocaleString()}
                    </span>
                  </div>
                )
              })}
            </div>
            <div className="border-t border-gray-700 pt-3 mt-3 shrink-0 flex justify-between items-center">
              <span className="text-gray-400 text-sm">合計</span>
              <span className={`font-bold text-lg ${showPaymentModal === 'card' ? 'text-blue-400' : 'text-purple-400'}`}>
                ¥{(showPaymentModal === 'card'
                  ? cardTickets.reduce((s: number, t: any) => s + (t.card_amount || 0), 0)
                  : codeTickets.reduce((s: number, t: any) => s + (t.code_amount || 0), 0)
                ).toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 未会計伝票ブロックポップアップ */}
      {showOpenTicketBlock && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-[70]">
          <div className="card max-w-sm w-full mx-4 space-y-4">
            <h4 className="font-bold text-white text-base">営業終了できません</h4>
            <p className="text-gray-300 text-sm leading-relaxed">
              未会計の伝票が <span className="text-yellow-400 font-bold">{openTicketCount}卓</span> 残っています。<br />
              すべての伝票を会計してから営業終了してください。
            </p>
            <div className="flex justify-end">
              <button onClick={() => setShowOpenTicketBlock(false)} className="btn-primary px-6">OK</button>
            </div>
          </div>
        </div>
      )}

      {/* 過不足金繰越確認ポップアップ */}
      {showCarryoverConfirm && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-[70]">
          <div className="card max-w-sm w-full mx-4 space-y-4">
            <h4 className="font-bold text-white text-center text-base">過不足金の繰越確認</h4>
            <p className="text-gray-300 text-sm text-center leading-relaxed">
              過不足金{' '}
              <span className={`font-bold text-base ${diff > 0 ? 'text-blue-300' : 'text-red-400'}`}>
                {diff > 0 ? '+' : ''}¥{diff.toLocaleString()}
              </span>{' '}
              を翌営業日に繰り越しますか？
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button onClick={() => { setShowCarryoverConfirm(false); doSubmit(null) }} className="btn-secondary">
                キャンセル
              </button>
              <button onClick={() => { setShowCarryoverConfirm(false); doSubmit(diff) }} className="btn-primary">
                はい
              </button>
            </div>
          </div>
        </div>
      )}

      {/* フッター */}
      <div className="shrink-0 grid grid-cols-2 gap-3 px-4 py-3 border-t border-gray-800">
        <button onClick={onClose} className="btn-secondary">キャンセル</button>
        <button onClick={handleSubmit} disabled={isPending} className="btn-danger text-base py-3">
          営業終了
        </button>
      </div>
    </div>
  )
}

// D時間: 種別×キャストごとに色分けして表示
// 全卓を横断してキャスト最新ドリンク時刻を集計（シャンパン除外）
function CrossTicketTimerContext({ tickets, children }: {
  tickets: any[]
  children: (map: Record<number, { ticketId: number; lastAt: string }>) => React.ReactNode
}) {
  const map = useMemo(() => {
    const out: Record<number, { ticketId: number; lastAt: string }> = {}
    for (const t of (tickets || [])) {
      const ldt = t.last_drink_times || {}
      for (const [type, arr] of Object.entries(ldt) as any[]) {
        if (type === 'champagne') continue
        if (!Array.isArray(arr)) continue
        for (const c of arr) {
          if (!c || c.cast_id == null || !c.last_at) continue
          const cur = out[c.cast_id]
          if (!cur || c.last_at > cur.lastAt) out[c.cast_id] = { ticketId: t.id, lastAt: c.last_at }
        }
      }
    }
    return out
  }, [tickets])
  return <>{children(map)}</>
}


function DrinkTimers({ lastDrinkTimes, now, ticketId, onCleared, castLatestMap, currentCastIds, onCastRemove }: {
  lastDrinkTimes: any; now: number; ticketId?: number; onCleared?: () => void
  castLatestMap?: Record<number, { ticketId: number; lastAt: string }>
  currentCastIds?: number[]
  onCastRemove?: (castId: number) => void
}) {
  const [confirming, setConfirming] = useState<string | null>(null) // key
  // key -> clearedAt (ms)。last_at がクリア時刻より新しければ再表示する
  const [clearedKeys, setClearedKeys] = useState<Map<string, number>>(new Map())
  // 「✖」押して複数接客として残すキャスト
  const [dismissedExpired, setDismissedExpired] = useState<Set<string>>(new Set())

  if (!lastDrinkTimes) return null

  const entries: { key: string; label: string; color: string; bg: string; lastAt: string; castId: number; drinkType: string }[] = []
  for (const [type, cfg] of Object.entries(DRINK_COLORS)) {
    const raw = lastDrinkTimes[type]
    if (!Array.isArray(raw) || raw.length === 0) continue
    for (const c of raw) {
      if (!c || typeof c !== 'object' || !c.last_at) continue
      const typeLabel = type === 'custom_menu' && c.item_name
        ? c.item_name.replace(/\[.*?\]/g, '').trim().charAt(0)
        : cfg.label
      const label = c.cast_name ? `${typeLabel}${c.cast_name}` : typeLabel
      entries.push({ key: `${type}-${c.cast_id ?? 0}`, label, color: cfg.color, bg: cfg.bg, lastAt: c.last_at, castId: c.cast_id, drinkType: type })
    }
  }

  if (entries.length === 0) return null

  const handleClear = (e: { castId: number; drinkType: string; key: string }) => {
    if (!ticketId) return
    setClearedKeys(prev => new Map([...prev, [e.key, Date.now()]]))
    setConfirming(null)
    apiClient.post(`/api/tickets/${ticketId}/drink-clear`, { cast_id: e.castId, drink_type: e.drinkType })
      .then(() => onCleared?.())
  }

  // 「完了」= タイマー消す + 対応中から外す（交代）
  const handleExpiredComplete = (e: { castId: number; drinkType: string; key: string }) => {
    setClearedKeys(prev => new Map([...prev, [e.key, Date.now()]]))
    if (onCastRemove && e.castId != null) onCastRemove(e.castId)
  }

  const isHidden = (e: { key: string; lastAt: string; castId: number }) => {
    const clearedAt = clearedKeys.get(e.key)
    const lastAtMs = new Date(e.lastAt.endsWith('Z') ? e.lastAt : e.lastAt + 'Z').getTime()
    if (clearedAt !== undefined && lastAtMs <= clearedAt) return true
    // キャストがこの卓の対応中でなければ非表示（ティッシュ配り等で外れた場合）
    // ただし対応中キャストが0人（未設定）の場合はフィルタしない
    if (currentCastIds && currentCastIds.length > 0 && e.castId != null && !currentCastIds.includes(e.castId)) return true
    // 他の卓で同じキャストにより新しい注文があれば、こちらは隠す
    if (castLatestMap && e.castId != null) {
      const latest = castLatestMap[e.castId]
      if (latest && latest.ticketId !== ticketId) {
        const latestMs = new Date(latest.lastAt.endsWith('Z') ? latest.lastAt : latest.lastAt + 'Z').getTime()
        if (latestMs > lastAtMs) return true
      }
    }
    return false
  }

  const visibleEntries = entries.filter(e => !isHidden(e))
  // 複数キャストがいて、30分超えのキャストがいるか判定
  const uniqueCastIds = new Set(visibleEntries.map(e => e.castId).filter(id => id != null))
  const hasMultipleCasts = uniqueCastIds.size > 1

  return (
    <div className="flex gap-2 flex-wrap">
      {visibleEntries.map(e => {
        const elapsed = calcElapsed(e.lastAt, now)
        const elapsedMin = elapsed / 1000 / 60
        const isExpired = hasMultipleCasts && elapsedMin >= 30 && !dismissedExpired.has(e.key)

        if (confirming === e.key) {
          return (
            <span key={e.key} className="flex items-center gap-1 text-xs">
              <span className={`${e.bg} ${e.color} px-1 rounded text-xs`}>{e.label}</span>
              <button onClick={() => handleClear(e)} className="text-green-400 font-bold px-1 hover:text-green-300">完了</button>
              <button onClick={() => setConfirming(null)} className="text-gray-500 px-1 hover:text-gray-300">×</button>
            </span>
          )
        }
        if (isExpired) {
          return (
            <span key={e.key} className="flex items-center gap-1 text-xs">
              <span className={`${e.bg} ${e.color} px-1 rounded text-xs opacity-60`}>{e.label}</span>
              <span className="text-gray-500 font-mono">{fmtTime(elapsed)}</span>
              <button onClick={() => handleExpiredComplete(e)} className="text-green-400 font-bold px-0.5 hover:text-green-300 text-[10px]">完了</button>
              <button onClick={() => setDismissedExpired(prev => new Set([...prev, e.key]))} className="text-gray-500 px-0.5 hover:text-gray-300 text-[10px]">✖</button>
            </span>
          )
        }
        return (
          <span key={e.key} className="flex items-center gap-1 text-xs font-mono cursor-pointer"
            onClick={() => setConfirming(e.key)}>
            <span className={`${e.bg} ${e.color} px-1 rounded text-xs`}>{e.label}</span>
            <span className={e.color}>{fmtTime(elapsed)}</span>
          </span>
        )
      })}
    </div>
  )
}

const PAYMENT_LABELS: Record<string, string> = { cash: '現金', card: 'カード', code: 'コード', mixed: '混合' }

function OrderLogsView({ storeId }: { storeId: number }) {
  const qc = useQueryClient()
  const [selectedLog, setSelectedLog] = useState<any | null>(null)
  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['order-logs', storeId],
    queryFn: () => apiClient.get('/api/tickets/logs', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
    refetchInterval: 10000,
  })

  const ACTION_LABELS: Record<string, string> = {
    cancel: '削除',
    update_quantity: '数量変更',
    change_start_time: '時間変更',
  }

  const actionColor = (action: string) =>
    action === 'cancel' ? 'bg-red-900/60 text-red-400'
    : action === 'change_start_time' ? 'bg-blue-900/60 text-blue-400'
    : 'bg-yellow-900/60 text-yellow-400'

  return (
    <div className="flex-1 overflow-y-auto min-h-0">
      <div className="p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-500">削除・変更履歴（直近200件）</p>
          <button onClick={() => qc.invalidateQueries({ queryKey: ['order-logs', storeId] })}
            className="text-xs text-gray-400 hover:text-white px-2 py-1 bg-gray-800 rounded-lg transition-colors">
            更新
          </button>
        </div>
        {isLoading && <p className="text-gray-500 text-sm">読み込み中...</p>}
        {!isLoading && logs.length === 0 && (
          <p className="text-center text-gray-500 py-16">履歴はありません</p>
        )}
        <div className="space-y-1">
          {logs.map((log: any) => (
            <div key={log.id}
              onClick={() => setSelectedLog(log)}
              className="flex items-center gap-3 px-3 py-2 bg-gray-900 border border-gray-800 rounded-xl text-sm cursor-pointer hover:border-gray-600 hover:bg-gray-800/60 transition-colors">
              <span className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full ${actionColor(log.action)}`}>
                {ACTION_LABELS[log.action] ?? log.action}
              </span>
              <span className="text-gray-400 text-xs shrink-0">{log.table_no ?? '—'}</span>
              <span className="text-white truncate max-w-[200px]">{log.item_name}</span>
              {log.action === 'cancel' ? (
                <span className="text-red-400 text-xs shrink-0">¥{(log.old_amount ?? 0).toLocaleString()}</span>
              ) : log.action === 'change_start_time' ? (
                <span className="text-blue-400 text-xs shrink-0">—</span>
              ) : (
                <span className="text-yellow-400 text-xs shrink-0">{log.old_quantity}→{log.new_quantity}</span>
              )}
              <span className="text-gray-600 text-xs shrink-0">{log.operator_name || log.changed_by_name || '—'}</span>
              {log.reason && <span className="text-gray-500 text-xs italic truncate max-w-[160px]">「{log.reason}」</span>}
              <span className="text-gray-600 text-xs shrink-0 ml-auto">
                {log.changed_at ? new Date(log.changed_at + 'Z').toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 詳細モーダル */}
      {selectedLog && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[300] p-4"
          onClick={() => setSelectedLog(null)}>
          <div className="bg-night-800 border border-night-600 rounded-2xl w-full max-w-sm shadow-2xl"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-night-600">
              <span className={`text-sm font-bold px-2.5 py-1 rounded-full ${actionColor(selectedLog.action)}`}>
                {ACTION_LABELS[selectedLog.action] ?? selectedLog.action}
              </span>
              <button onClick={() => setSelectedLog(null)}><X className="w-5 h-5 text-gray-400" /></button>
            </div>
            <div className="px-5 py-4 space-y-3">
              {[
                { label: '卓番', value: selectedLog.table_no ?? '—' },
                { label: '品目', value: selectedLog.item_name ?? '—' },
                selectedLog.action === 'cancel'
                  ? { label: '金額', value: `¥${(selectedLog.old_amount ?? 0).toLocaleString()}` }
                  : selectedLog.action === 'update_quantity'
                  ? { label: '数量変更', value: `${selectedLog.old_quantity} → ${selectedLog.new_quantity}` }
                  : null,
                selectedLog.action === 'cancel'
                  ? { label: '数量', value: `${selectedLog.old_quantity}` }
                  : null,
                { label: '担当者', value: selectedLog.operator_name || selectedLog.changed_by_name || '—' },
                { label: '理由', value: selectedLog.reason || '—' },
                { label: '日時', value: selectedLog.changed_at ? new Date(selectedLog.changed_at + 'Z').toLocaleString('ja-JP') : '—' },
              ].filter(Boolean).map((row: any) => (
                <div key={row.label} className="flex gap-3">
                  <span className="text-gray-500 text-sm w-20 shrink-0">{row.label}</span>
                  <span className="text-white text-sm break-all">{row.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ClosedTicketHistory({ storeId, onDetail }: { storeId: number; onDetail: (id: number) => void }) {
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 10)
  })
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10))
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: closed = [], isLoading } = useQuery({
    queryKey: ['tickets', storeId, 'closed', dateFrom, dateTo],
    queryFn: () => apiClient.get('/api/tickets', { params: { store_id: storeId, is_closed: true } }).then(r => r.data),
    enabled: !!storeId,
  })

  const filtered = (closed as any[]).filter(t => {
    const ms = toUtcMs(t.ended_at || t.started_at)
    if (!ms) return true
    const d = new Date(ms).toISOString().slice(0, 10)
    return d >= dateFrom && d <= dateTo
  }).sort((a: any, b: any) => {
    const ma = toUtcMs(b.ended_at || b.started_at) ?? 0
    const mb = toUtcMs(a.ended_at || a.started_at) ?? 0
    return ma - mb
  })

  const totalAmount = filtered.reduce((s: number, t: any) => s + calcTicketGrandTotal(t), 0)

  return (
    <div className="flex-1 overflow-y-auto min-h-0">
      {/* フィルター */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="input-field text-sm" />
        <span className="text-gray-500">〜</span>
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="input-field text-sm" />
        <span className="text-gray-400 text-sm ml-2">{filtered.length}件</span>
        <span className="text-white font-bold text-sm">合計 ¥{totalAmount.toLocaleString()}</span>
      </div>

      {isLoading && <div className="text-gray-500 text-sm py-8 text-center">読み込み中...</div>}

      <div className="space-y-2">
        {filtered.map((ticket: any) => {
          const endMs = toUtcMs(ticket.ended_at)
          const startMs = toUtcMs(ticket.started_at)
          const endDate = endMs ? new Date(endMs) : null
          const startDate = startMs ? new Date(startMs) : null
          const isExpanded = expandedId === ticket.id
          return (
            <div key={ticket.id} className="card">
              <div className="flex items-center gap-3 cursor-pointer" onClick={() => setExpandedId(isExpanded ? null : ticket.id)}>
                {/* 日付・時刻 */}
                <div className="shrink-0 text-xs text-gray-500 w-24">
                  {endDate ? (
                    <>
                      <div>{endDate.toLocaleDateString('ja-JP', { month: '2-digit', day: '2-digit' })}</div>
                      <div>{toBarHour(endDate.getHours()).toString().padStart(2,'0')}:{endDate.getMinutes().toString().padStart(2,'0')} 退店</div>
                    </>
                  ) : '—'}
                </div>
                {/* 卓・プラン */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-white">{ticket.table_no || '—'}</span>
                    {ticket.visit_type && <span className={`badge text-xs ${ticket.visit_type === 'N' ? 'bg-blue-900/40 text-blue-400' : 'bg-purple-900/40 text-purple-400'}`}>{ticket.visit_type}</span>}
                    {ticket.plan_type && <span className={`badge text-xs ${ticket.plan_type === 'premium' ? 'bg-yellow-900/40 text-yellow-400' : 'bg-gray-700 text-gray-400'}`}>{ticket.plan_type === 'premium' ? 'P' : 'S'}</span>}
                    <span className="text-xs text-gray-500">{ticket.guest_count}名</span>
                    {ticket.visit_motivation && <span className="badge text-xs bg-teal-900/40 text-teal-400">{ticket.visit_motivation}</span>}
                    {ticket.customer_name && <span className="text-xs text-gray-400 truncate">{ticket.customer_name}</span>}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {startDate ? `${toBarHour(startDate.getHours()).toString().padStart(2,'0')}:${startDate.getMinutes().toString().padStart(2,'0')} 入店` : ''}
                    {(() => {
                      const guest = Math.max(1, ticket.guest_count || 1)
                      const totalQty = (ticket.order_items || [])
                        .filter((i: any) => i.item_type === 'extension' && !i.canceled_at && !(i.item_name || '').startsWith('合流'))
                        .reduce((s: number, i: any) => s + (i.quantity || 0), 0)
                      const periods = Math.floor(totalQty / guest)
                      return periods > 0 ? <span className="ml-2">延長{periods}回</span> : null
                    })()}
                  </div>
                </div>
                {/* 金額・支払方法 */}
                <div className="shrink-0 text-right">
                  <div className="font-bold text-pink-400">¥{calcTicketGrandTotal(ticket).toLocaleString()}</div>
                  <div className="text-xs text-gray-500">
                    {PAYMENT_LABELS[ticket.payment_method] ?? ticket.payment_method ?? '—'}
                    {(ticket.order_items || []).some((i: any) => i.item_name?.startsWith('先会計') && !i.canceled_at) && (
                      <span className="ml-1 text-orange-400">+先会計</span>
                    )}
                  </div>
                </div>
                <span className="text-gray-600 text-xs ml-1">{isExpanded ? '▲' : '▼'}</span>
              </div>

              {/* 展開: 注文明細 */}
              {isExpanded && (
                <div className="mt-3 border-t border-gray-700 pt-3 space-y-3">
                  <div className="grid grid-cols-3 gap-1 text-xs">
                    {(ticket.order_items || []).filter((i: any) => !(i.item_type === 'champagne' && i.unit_price === 0)).map((item: any) => (
                      <div key={item.id} className={`flex justify-between px-2 py-1 rounded ${item.canceled_at ? 'opacity-40' : 'bg-gray-800'}`}>
                        <span className={`truncate ${item.canceled_at ? 'line-through text-gray-500' : 'text-gray-300'}`}>{item.item_name || item.item_type} ×{item.quantity}</span>
                        <span className="text-gray-400 shrink-0 ml-1">¥{item.amount.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                  <button onClick={() => onDetail(ticket.id)}
                    className="text-xs text-pink-400 hover:text-pink-300 transition-colors">
                    詳細を開く →
                  </button>
                </div>
              )}
            </div>
          )
        })}
        {!isLoading && filtered.length === 0 && (
          <div className="text-center text-gray-500 py-16">該当する会計済み伝票はありません</div>
        )}
      </div>
    </div>
  )
}

function TicketCard({ ticket, storeId, onClick, onOpenCustomerModal, onOpenCastModal, onOpenActiveCastsModal, castLatestMap }: {
  ticket: any; storeId: number; onClick: () => void
  onOpenCustomerModal: (ticket: any) => void
  onOpenCastModal: (ticket: any) => void
  onOpenActiveCastsModal: (ticket: any) => void
  castLatestMap?: Record<number, { ticketId: number; lastAt: string }>
}) {
  const qc = useQueryClient()
  const now = useNow()
  const elapsed = calcElapsed(ticket.set_started_at || ticket.started_at, now)
  const setElapsed = calcSetElapsed(ticket, now)
  const eElapsed = ticket.e_started_at !== null ? calcElapsed(ticket.e_started_at, now) : null
  const startedAtMs = toUtcMs(ticket.started_at)
  const startedAt = startedAtMs ? new Date(startedAtMs) : new Date()

  const [showEditBtn, setShowEditBtn] = useState(false)
  const [editingTime, setEditingTime] = useState(false)
  const [editHour, setEditHour] = useState(toBarHour(startedAt.getHours()))
  const [editMin, setEditMin] = useState(startedAt.getMinutes())
  const [showLog, setShowLog] = useState(false)

  const saveTime = (e: React.MouseEvent) => {
    e.stopPropagation()
    const base = new Date(startedAt)
    base.setHours(fromBarHour(editHour), editMin, 0, 0)
    const utcIso = base.toISOString()
    apiClient.patch(`/api/tickets/${ticket.id}`, { started_at: utcIso }).then(() => {
      qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
      qc.invalidateQueries({ queryKey: ['ticket', ticket.id] })
    })
    setEditingTime(false)
    setShowEditBtn(false)
  }

  return (
    <div
      onClick={e => { if (!(e.target as HTMLElement).closest('[data-nopropagate]')) onClick() }}
      className="card text-left flex flex-col hover:border-primary-600/50 transition-colors shrink-0 cursor-pointer w-full md:w-[220px]"
    >
      {/* 卓番・経過時間・ログボタン */}
      <div className="flex justify-between items-start mb-1">
        <p className="text-lg font-bold text-white">{ticket.table_no || '—'}</p>
        <div className="flex items-center gap-2">
          <button
            data-nopropagate
            onClick={e => { e.stopPropagation(); setShowLog(true) }}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-gray-500 rounded-lg px-2 py-0.5 transition-colors shrink-0"
          >
            <ClipboardList className="w-3.5 h-3.5" />
            ログ
          </button>
          <div className="flex items-center gap-1 font-mono text-sm">
            <span className="text-gray-500 text-xs">経過</span>
            <span className="text-green-400">{fmtTime(elapsed)}</span>
          </div>
        </div>
      </div>

      {/* バッジ（クリックで詳細モーダルを開く） */}
      <div className="flex gap-1 flex-wrap mb-2" data-nopropagate>
        <button onClick={e => { e.stopPropagation(); onClick() }}
          className={`badge text-xs ${ticket.visit_type === 'N' ? 'bg-blue-900/40 text-blue-400' : ticket.visit_type === 'R' ? 'bg-purple-900/40 text-purple-400' : 'bg-night-700 text-gray-500'} hover:opacity-80`}
        >{ticket.visit_type || 'N/R'}</button>
        <button onClick={e => { e.stopPropagation(); onClick() }}
          className={`badge text-xs ${ticket.plan_type === 'premium' ? 'bg-yellow-900/40 text-yellow-400' : 'bg-gray-700 text-gray-400'} hover:opacity-80`}
        >{ticket.plan_type === 'premium' ? 'プレミアム' : 'スタンダード'}</button>
        <button onClick={e => { e.stopPropagation(); onClick() }}
          className="badge text-xs bg-night-600 text-gray-300 hover:opacity-80"
        >{ticket.guest_count || 1}名様</button>
        {ticket.visit_motivation && (
          <button onClick={e => { e.stopPropagation(); onClick() }}
            className="badge text-xs bg-teal-900/40 text-teal-400 hover:opacity-80"
          >
            {ticket.visit_motivation}
            {ticket.motivation_cast_name && `／${ticket.motivation_cast_name}`}
            {ticket.motivation_note && `／${ticket.motivation_note}`}
          </button>
        )}
      </div>

      {/* 顧客・キャスト */}
      <div className="flex flex-col gap-0.5 text-xs mb-2">
        <button onClick={e => { e.stopPropagation(); onOpenCustomerModal(ticket) }}
          className="w-fit text-left text-gray-400 hover:text-white transition-colors underline decoration-dotted">
          {ticket.customer_name || '顧客未設定'}
        </button>
        <button onClick={e => { e.stopPropagation(); onOpenCastModal(ticket) }}
          className="w-fit text-left text-primary-400 hover:text-primary-300 transition-colors underline decoration-dotted">
          {ticket.featured_cast_name || '担当未設定'}
        </button>
        <button onClick={e => { e.stopPropagation(); onOpenActiveCastsModal(ticket) }}
          className="w-fit text-left text-purple-300 hover:text-purple-200 transition-colors underline decoration-dotted text-[10px]">
          {(ticket.current_casts && ticket.current_casts.length > 0)
            ? `対応中: ${ticket.current_casts.map((c: any) => c.cast_name).join('・')}`
            : '対応中未設定'}
        </button>
      </div>

      {/* E/残り時間タイマー */}
      <div className="flex gap-3 text-xs font-mono mb-1">
        <span className="text-gray-500">E <span className={eElapsed !== null ? 'text-orange-400' : 'text-gray-600'}>{eElapsed !== null ? fmtTime(eElapsed) : '—'}</span></span>
        {setElapsed === null
          ? <span className="text-gray-600 text-xs">▶ 開始待ち</span>
          : (() => {
              const countdown = calcSetCountdown(setElapsed)!
              const urgent = countdown <= 5 * 60
              return (
                <div className="flex items-baseline gap-1">
                  <span className="text-gray-500 text-xs">残り</span>
                  <span className={`font-mono font-bold text-3xl ${ticket.set_is_paused ? 'text-yellow-400' : urgent ? 'text-red-400' : 'text-green-400'}`}>{fmtTime(countdown)}</span>
                </div>
              )
            })()
        }
      </div>

      {/* D時間 */}
      <div className="mb-3" data-nopropagate>
        <DrinkTimers lastDrinkTimes={ticket.last_drink_times} now={now} ticketId={ticket.id}
          castLatestMap={castLatestMap}
          currentCastIds={(ticket.current_casts || []).map((c: any) => c.cast_id).filter((id: any) => id != null)}
          onCleared={() => { qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] }) }}
          onCastRemove={(castId) => {
            const remaining = (ticket.current_casts || []).map((c: any) => c.cast_id).filter((id: any) => id != null && id !== castId)
            apiClient.post(`/api/tickets/${ticket.id}/assignments/set`, { cast_ids: remaining }).then(() => {
              qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
            })
          }} />
      </div>

      {/* 注文明細 */}
      <div className="flex-1 border-t border-night-700 pt-2 mb-2">
        <div className="flex items-center gap-1 mb-1" data-nopropagate>
          {editingTime ? (
            <>
              <select value={editHour} onChange={e => setEditHour(Number(e.target.value))}
                className="input-field text-xs py-0.5 px-1 w-16">
                {!BAR_HOURS.includes(editHour) && (
                  <option value={editHour}>{String(editHour).padStart(2,'0')}</option>
                )}
                {BAR_HOURS.map(n => <option key={n} value={n}>{String(n).padStart(2,'0')}</option>)}
              </select>
              <span className="text-gray-500 text-xs">:</span>
              <select value={editMin} onChange={e => setEditMin(Number(e.target.value))}
                className="input-field text-xs py-0.5 px-1 w-14">
                {Array.from({ length: 60 }, (_, i) => <option key={i} value={i}>{i.toString().padStart(2,'0')}</option>)}
              </select>
              <button onClick={saveTime} className="text-xs bg-primary-600 hover:bg-primary-500 text-white px-1.5 py-0.5 rounded">保存</button>
              <button onClick={e => { e.stopPropagation(); setEditingTime(false); setShowEditBtn(false) }} className="text-xs text-gray-500">×</button>
            </>
          ) : (
            <>
              <span
                className="text-xs text-gray-500 cursor-pointer hover:text-gray-300"
                onClick={e => { e.stopPropagation(); setShowEditBtn(v => !v) }}
              >
                {toBarHour(startedAt.getHours()).toString().padStart(2,'0')}:{startedAt.getMinutes().toString().padStart(2,'0')} 入店
              </span>
              {showEditBtn && (
                <button onClick={e => { e.stopPropagation(); setEditHour(toBarHour(startedAt.getHours())); setEditMin(startedAt.getMinutes()); setEditingTime(true) }}
                  className="text-xs text-primary-400 hover:text-primary-300 underline ml-1">編集</button>
              )}
            </>
          )}
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-600">
              <th className="text-left pb-1">品目</th>
              <th className="text-center pb-1">数</th>
              <th className="text-right pb-1">金額</th>
            </tr>
          </thead>
          <tbody>
            {(() => {
              const items = ticket.order_items || []
              if (items.length === 0) return <tr><td colSpan={3} className="text-gray-600 py-2">注文なし</td></tr>
              // 同じ item_name をグルーピング
              const grouped: { name: string; qty: number; amount: number; item: any }[] = []
              for (const item of items) {
                const name = displayItemName(item)
                const existing = grouped.find(g => g.name === name)
                if (existing) {
                  existing.qty += (item.quantity || 1)
                  existing.amount += (item.amount || 0)
                } else {
                  grouped.push({ name, qty: item.quantity || 1, amount: item.amount || 0, item })
                }
              }
              return grouped.map((g, i) => (
                <tr key={i} className="border-t border-night-700/30">
                  <td className="text-gray-300 py-0.5 truncate max-w-[100px]">{g.name}</td>
                  <td className="text-center text-gray-500 py-0.5">{g.qty}</td>
                  <td className="text-right text-gray-300 py-0.5">¥{g.amount.toLocaleString()}</td>
                </tr>
              ))
            })()}
          </tbody>
        </table>
      </div>

      {/* 合計 */}
      {(() => {
        const sk = (ticket.order_items || [])
          .filter((i: any) => (i.item_name?.startsWith('先会計') || i.item_name?.startsWith('分割清算') || i.item_name?.startsWith('値引き')) && !i.canceled_at)
          .reduce((s: number, i: any) => s + Math.abs(i.amount), 0)
        const sub = ticket.total_amount + sk
        const grand = Math.round(sub * 1.21) - sk
        return (
          <div className="border-t border-night-600 pt-2 space-y-0.5">
            <p className="text-xs text-gray-400">延長 {(() => {
              const guest = Math.max(1, ticket.guest_count || 1)
              const totalQty = (ticket.order_items || [])
                .filter((i: any) => i.item_type === 'extension' && !i.canceled_at && !(i.item_name || '').startsWith('合流'))
                .reduce((s: number, i: any) => s + (i.quantity || 0), 0)
              return Math.floor(totalQty / guest)
            })()}回</p>
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">小計</span>
              <span className="text-sm text-gray-400">¥{sub.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">サービス料10%／消費税10%</span>
              <span className="text-xl font-bold text-primary-400">¥{grand.toLocaleString()}</span>
            </div>
          </div>
        )
      })()}

      <div data-nopropagate>
        {showLog && (
          <TicketLogModal ticket={ticket} onClose={() => setShowLog(false)} />
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────
// 伝票操作ログモーダル
// ─────────────────────────────────────────
function TicketLogModal({ ticket, onClose }: { ticket: any; onClose: () => void }) {
  // タイムラインイベントを集約して時刻順に並べる
  const events: { time: string; label: string; sub?: string; color: string }[] = []

  const addEvent = (isoStr: string | null | undefined, label: string, sub?: string, color = 'text-gray-300') => {
    if (!isoStr) return
    events.push({ time: isoStr, label, sub, color })
  }

  addEvent(ticket.started_at, '入店', undefined, 'text-green-400')
  addEvent(ticket.set_started_at, 'セット開始（飲み放題）', undefined, 'text-blue-400')
  addEvent(ticket.e_started_at, '延長開始', undefined, 'text-orange-400')

  // オーダーアイテム
  for (const item of ticket.order_items || []) {
    if (!item.created_at) continue
    const canceled = !!item.canceled_at
    const name = item.item_name || item.item_type || '—'
    addEvent(
      item.created_at,
      canceled ? `[取消] ${name}` : name,
      item.quantity > 1 ? `×${item.quantity}  ¥${item.amount.toLocaleString()}` : `¥${item.amount.toLocaleString()}`,
      canceled ? 'text-gray-600 line-through' : 'text-gray-200'
    )
    if (canceled) addEvent(item.canceled_at, `取消: ${name}`, undefined, 'text-red-500')
  }

  // ドリンクスタンプ（last_drink_times）※custom_menuはオーダーと重複するため除外
  if (ticket.last_drink_times) {
    for (const [type, arr] of Object.entries(ticket.last_drink_times as Record<string, any[]>)) {
      if (type === 'custom_menu') continue
      if (!Array.isArray(arr)) continue
      for (const c of arr) {
        if (!c?.last_at) continue
        const cfg = (DRINK_COLORS as any)[type]
        const label = cfg ? `${cfg.label}スタンプ${c.cast_name ? `（${c.cast_name}）` : ''}` : `${type}スタンプ`
        addEvent(c.last_at, label, undefined, cfg?.color || 'text-yellow-400')
      }
    }
  }

  // 時刻順ソート
  events.sort((a, b) => a.time.localeCompare(b.time))

  const toJst = (iso: string) => {
    const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
    const h = ((d.getUTCHours() + 9) % 24).toString().padStart(2, '0')
    const m = d.getUTCMinutes().toString().padStart(2, '0')
    return `${h}:${m}`
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[200] p-4" onClick={e => { e.stopPropagation(); onClose() }}>
      <div className="card w-full max-w-sm max-h-[80vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-3 shrink-0">
          <div>
            <h4 className="font-bold text-white text-base">{ticket.table_no} — 操作ログ</h4>
            <p className="text-xs text-gray-500">{ticket.customer_name || '顧客未設定'}</p>
          </div>
          <button onClick={e => { e.stopPropagation(); onClose() }}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {events.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-8">ログがありません</p>
          ) : (
            <div className="relative pl-4">
              {/* 縦線 */}
              <div className="absolute left-1.5 top-0 bottom-0 w-px bg-gray-700" />
              <div className="space-y-3">
                {events.map((ev, i) => (
                  <div key={i} className="flex items-start gap-3 relative">
                    {/* ドット */}
                    <div className="absolute -left-2.5 top-1.5 w-2 h-2 rounded-full bg-gray-600 shrink-0" />
                    <span className="text-xs text-gray-500 font-mono shrink-0 w-10">{toJst(ev.time)}</span>
                    <div className="min-w-0">
                      <span className={`text-sm font-medium ${ev.color}`}>{ev.label}</span>
                      {ev.sub && <span className="text-xs text-gray-500 ml-1.5">{ev.sub}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const MOTIVATION_OPTIONS = ['ティッシュ', 'SNS', 'LINE', '紹介', 'Google', '看板', '電話']
const MOTIVATION_CAST_REQUIRED = new Set(['ティッシュ', 'LINE'])

function NewTicketModal({ storeId, onSubmit, onClose }: {
  storeId: number
  onSubmit: (data: {
    tableNo: string; guestCount: number; planType: string; visitType: string
    visitMotivation?: string; motivationCastId?: number | null; motivationNote?: string
  }) => void
  onClose: () => void
}) {
  const [tableNo, setTableNo] = useState(TABLE_NOS[0])
  const [guestCount, setGuestCount] = useState(1)
  const [planType, setPlanType] = useState('premium')
  const [visitType, setVisitType] = useState('N')
  const [motivation, setMotivation] = useState('')
  const [motivationCastId, setMotivationCastId] = useState<number | null>(null)
  const [motivationNote, setMotivationNote] = useState('')

  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const casts = (castsAll as any[]).filter((c: any) => c.is_active)

  const needsCast = MOTIVATION_CAST_REQUIRED.has(motivation)
  const needsNote = motivation === '紹介'

  const row = "flex items-center gap-2"
  const label = "text-xs text-gray-400 w-20 shrink-0"

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-2.5">
        <div className="flex justify-between items-center mb-1">
          <h3 className="font-bold text-white">新規伝票</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        <div className={row}>
          <span className={label}>卓番号</span>
          <select value={tableNo} onChange={e => setTableNo(e.target.value)} className="input-field flex-1 text-sm py-1.5">
            {TABLE_NOS.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div className={row}>
          <span className={label}>客数</span>
          <select value={guestCount} onChange={e => setGuestCount(Number(e.target.value))} className="input-field flex-1 text-sm py-1.5">
            {Array.from({length: 20}, (_, i) => i + 1).map(n => <option key={n} value={n}>{n}名</option>)}
          </select>
        </div>

        <div className={row}>
          <span className={label}>プラン</span>
          <div className="flex gap-1.5 flex-1">
            {['premium', 'standard'].map(p => (
              <button key={p} onClick={() => setPlanType(p)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${planType === p ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                {p === 'premium' ? 'プレミアム' : 'スタンダード'}
              </button>
            ))}
          </div>
        </div>

        <div className={row}>
          <span className={label}>区分</span>
          <div className="flex gap-1.5 flex-1">
            {['N', 'R'].map(v => (
              <button key={v} onClick={() => setVisitType(v)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${visitType === v ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                {v}
              </button>
            ))}
          </div>
        </div>

        <div className={row}>
          <span className={label}>来店動機</span>
          <select value={motivation} onChange={e => { setMotivation(e.target.value); setMotivationCastId(null); setMotivationNote('') }}
            className="input-field flex-1 text-sm py-1.5">
            <option value="">未選択</option>
            {MOTIVATION_OPTIONS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {needsCast && (
          <div className={row}>
            <span className={label}>キャスト</span>
            <select value={motivationCastId ?? ''} onChange={e => setMotivationCastId(e.target.value ? Number(e.target.value) : null)}
              className="input-field flex-1 text-sm py-1.5">
              <option value="">選択してください</option>
              {casts.map((c: any) => <option key={c.id} value={c.id}>{c.stage_name}</option>)}
            </select>
          </div>
        )}

        {needsNote && (
          <div className={row}>
            <span className={label}>紹介者</span>
            <input type="text" value={motivationNote} onChange={e => setMotivationNote(e.target.value)}
              placeholder="紹介者名を入力"
              className="input-field flex-1 text-sm py-1.5" />
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => onSubmit({
            tableNo, guestCount, planType, visitType,
            visitMotivation: motivation || undefined,
            motivationCastId: needsCast ? motivationCastId : null,
            motivationNote: needsNote ? motivationNote : undefined,
          })} className="btn-primary flex-1">開始</button>
        </div>
      </div>
    </div>
  )
}

function CustomerSearchModal({ storeId, currentId, onSelect, onClose }: {
  storeId: number
  currentId: number | null
  onSelect: (id: number | null) => void
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', alias: '', phone: '' })
  const [adding, setAdding] = useState(false)

  const { data: customers = [] } = useQuery({
    queryKey: ['customers', storeId],
    queryFn: () => apiClient.get('/api/customers', { params: { store_id: storeId } }).then(r => r.data),
  })
  const filtered = (customers as any[]).filter((c: any) =>
    !q || c.name?.includes(q) || c.alias?.includes(q) || c.phone?.includes(q)
  ).slice(0, 30)

  const handleAddCustomer = async () => {
    if (!newForm.name.trim()) return
    setAdding(true)
    try {
      const res = await apiClient.post('/api/customers', {
        name: newForm.name.trim(),
        alias: newForm.alias.trim() || undefined,
        phone: newForm.phone.trim() || undefined,
      })
      await qc.invalidateQueries({ queryKey: ['customers', storeId] })
      onSelect(res.data.id)
      onClose()
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={e => { e.stopPropagation(); onClose() }}>
      <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">顧客を選択</h3>
          <button onClick={e => { e.stopPropagation(); onClose() }}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        {!showAdd ? (
          <>
            <div className="flex gap-2">
              <input type="text" value={q} onChange={e => setQ(e.target.value)}
                placeholder="名前・電話番号で検索"
                className="input-field flex-1 text-sm" autoFocus />
              <button
                onClick={e => { e.stopPropagation(); setShowAdd(true) }}
                className="btn-primary text-sm px-3 flex items-center gap-1 whitespace-nowrap"
              >
                <Plus className="w-3.5 h-3.5" />新規
              </button>
            </div>
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {currentId && (
                <button onClick={e => { e.stopPropagation(); onSelect(null); onClose() }}
                  className="w-full text-left px-3 py-2 rounded-lg text-xs text-gray-500 hover:bg-gray-800 transition-colors">
                  未設定に戻す
                </button>
              )}
              {filtered.map((c: any) => (
                <button key={c.id} onClick={e => { e.stopPropagation(); onSelect(c.id); onClose() }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${c.id === currentId ? 'bg-primary-700 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-200'}`}>
                  <span className="font-medium">{c.name}</span>
                  {c.alias && <span className="text-gray-400 text-xs ml-2">({c.alias})</span>}
                  {c.phone && <span className="text-gray-500 text-xs ml-2">{c.phone}</span>}
                </button>
              ))}
              {filtered.length === 0 && <p className="text-center text-gray-500 text-sm py-4">該当なし</p>}
            </div>
          </>
        ) : (
          <>
            <p className="text-xs text-gray-400">新規顧客を登録して伝票に紐づけます</p>
            <div className="space-y-2">
              <input
                type="text"
                value={newForm.name}
                onChange={e => setNewForm(f => ({ ...f, name: e.target.value }))}
                placeholder="名前 *"
                className="input-field w-full text-sm"
                autoFocus
              />
              <input
                type="text"
                value={newForm.alias}
                onChange={e => setNewForm(f => ({ ...f, alias: e.target.value }))}
                placeholder="ニックネーム（任意）"
                className="input-field w-full text-sm"
              />
              <input
                type="tel"
                value={newForm.phone}
                onChange={e => setNewForm(f => ({ ...f, phone: e.target.value }))}
                placeholder="電話番号（任意）"
                className="input-field w-full text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={e => { e.stopPropagation(); setShowAdd(false) }}
                className="btn-secondary flex-1 text-sm"
              >
                戻る
              </button>
              <button
                onClick={e => { e.stopPropagation(); handleAddCustomer() }}
                disabled={!newForm.name.trim() || adding}
                className="btn-primary flex-1 text-sm disabled:opacity-40"
              >
                {adding ? '登録中...' : '登録して選択'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// 担当（推しキャスト）= 1人だけ選択
function CastAssignModal({ storeId, currentCastName, onSelect, onClose }: {
  storeId: number
  currentCastName: string | null
  onSelect: (id: number | null) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const casts = (castsAll as any[]).filter((c: any) => c.is_active)
  const filtered = casts.filter((c: any) => !q || c.stage_name?.includes(q))

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={e => { e.stopPropagation(); onClose() }}>
      <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">担当（推しキャスト）を設定</h3>
          <button onClick={e => { e.stopPropagation(); onClose() }}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <input type="text" value={q} onChange={e => setQ(e.target.value)}
          placeholder="キャスト名で検索"
          className="input-field w-full text-sm" autoFocus />
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {currentCastName && (
            <button onClick={e => { e.stopPropagation(); onSelect(null); onClose() }}
              className="w-full text-left px-3 py-2 rounded-lg text-xs text-gray-500 hover:bg-gray-800 transition-colors">
              担当を外す
            </button>
          )}
          {filtered.map((c: any) => (
            <button key={c.id} onClick={e => { e.stopPropagation(); onSelect(c.id); onClose() }}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${c.stage_name === currentCastName ? 'bg-primary-700 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-200'}`}>
              <span className="font-medium">{c.stage_name}</span>
            </button>
          ))}
          {filtered.length === 0 && <p className="text-center text-gray-500 text-sm py-4">該当なし</p>}
        </div>
      </div>
    </div>
  )
}

// 伝票削除確認モーダル
function TicketDeleteModal({ ticket, onSubmit, onClose }: {
  ticket: any
  onSubmit: (operator: string, reason: string) => void
  onClose: () => void
}) {
  const [operator, setOperator] = useState('')
  const [reason, setReason] = useState('')
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[80] p-4" onClick={onClose}>
      <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-red-300">伝票を削除</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="text-xs text-gray-400 bg-red-900/20 border border-red-800/50 rounded-lg p-2 space-y-0.5">
          <div>卓: <span className="text-white font-medium">{ticket?.table_no || '—'}</span></div>
          <div>合計: <span className="text-white font-medium">¥{(ticket?.total_amount || 0).toLocaleString()}</span></div>
          <div className="text-[10px] text-red-400">※削除すると売上集計・日報から除外されます</div>
        </div>
        <input
          type="text" placeholder="担当者名（必須）"
          value={operator} onChange={e => setOperator(e.target.value)}
          className="input-field w-full text-sm" autoFocus
        />
        <input
          type="text" placeholder="理由（任意）"
          value={reason} onChange={e => setReason(e.target.value)}
          className="input-field w-full text-sm"
        />
        <div className="flex gap-2 justify-end">
          <button onClick={onClose}
            className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg">
            キャンセル
          </button>
          <button
            onClick={() => onSubmit(operator, reason)}
            disabled={!operator.trim()}
            className="text-xs px-4 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg disabled:opacity-40">
            削除する
          </button>
        </div>
      </div>
    </div>
  )
}


// ティッシュ配り開始モーダル（出勤中キャストから複数選択）
function TissueStartModal({ storeId, onClose, onStarted }: {
  storeId: number
  onClose: () => void
  onStarted: () => void
}) {
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const { data: workingAttendance = [] } = useQuery({
    queryKey: ['attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/attendance/working/${storeId}`).then(r => r.data),
    staleTime: 30000,
  })
  const { data: activeTissue = [] } = useQuery({
    queryKey: ['tissue-active', storeId],
    queryFn: () => apiClient.get('/api/tissue/active', { params: { store_id: storeId } }).then(r => r.data),
  })
  const workingCastIds = new Set(
    (workingAttendance as any[])
      .filter((a: any) => a.cast_id != null && !a.actual_end && !a.is_absent)
      .map((a: any) => a.cast_id)
  )
  const busyTissueCastIds = new Set((activeTissue as any[]).map((t: any) => t.cast_id))
  const casts = (castsAll as any[]).filter((c: any) => c.is_active && workingCastIds.has(c.id) && !busyTissueCastIds.has(c.id))
  const filtered = casts.filter((c: any) => !q || c.stage_name?.includes(q))

  const toggle = (cid: number) => {
    if (selected.includes(cid)) setSelected(selected.filter(x => x !== cid))
    else setSelected([...selected, cid])
  }

  const submit = () => {
    if (selected.length === 0) return
    apiClient.post('/api/tissue/start', { store_id: storeId, cast_ids: selected })
      .then(() => onStarted())
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={e => { e.stopPropagation(); onClose() }}>
      <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">ティッシュ配り開始</h3>
          <button onClick={e => { e.stopPropagation(); onClose() }}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <input type="text" value={q} onChange={e => setQ(e.target.value)}
          placeholder="キャスト名で検索" className="input-field w-full text-sm" autoFocus />
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {filtered.map((c: any) => {
            const isSelected = selected.includes(c.id)
            return (
              <button key={c.id} onClick={e => { e.stopPropagation(); toggle(c.id) }}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${isSelected ? 'bg-amber-700 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-200'}`}>
                <span className={`inline-block w-3.5 h-3.5 border rounded ${isSelected ? 'bg-white border-white' : 'border-gray-500'}`}>
                  {isSelected && <span className="block w-full h-full text-amber-700 text-[10px] leading-3 text-center">✓</span>}
                </span>
                <span className="font-medium">{c.stage_name}</span>
              </button>
            )
          })}
          {filtered.length === 0 && <p className="text-center text-gray-500 text-sm py-4">対象キャストがいません</p>}
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={e => { e.stopPropagation(); onClose() }}
            className="text-xs px-3 py-1.5 text-gray-400 hover:text-gray-200">キャンセル</button>
          <button onClick={e => { e.stopPropagation(); submit() }}
            disabled={selected.length === 0}
            className="text-xs px-4 py-1.5 bg-amber-700 hover:bg-amber-600 text-white rounded-lg disabled:opacity-40">
            開始（{selected.length}名）
          </button>
        </div>
      </div>
    </div>
  )
}


// 対応中キャスト = 出勤中から複数選択
function ActiveCastsModal({ storeId, currentCastIds, ticketId, onSubmit, onClose }: {
  storeId: number
  currentCastIds: number[]
  ticketId: number
  onSubmit: (ids: number[]) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<number[]>(currentCastIds)
  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const { data: workingAttendance = [] } = useQuery({
    queryKey: ['attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/attendance/working/${storeId}`).then(r => r.data),
    staleTime: 30000,
  })
  const workingCastIds = new Set(
    (workingAttendance as any[])
      .filter((a: any) => a.cast_id != null && !a.actual_end && !a.is_absent)
      .map((a: any) => a.cast_id)
  )
  const { data: openTickets = [] } = useQuery({
    queryKey: ['tickets', storeId, 'open'],
    queryFn: () => apiClient.get('/api/tickets', { params: { store_id: storeId, is_closed: false } }).then(r => r.data),
    staleTime: 5000,
  })
  const castOnOtherTable: Record<number, string> = {}
  for (const t of (openTickets as any[])) {
    if (t.id === ticketId) continue
    for (const c of (t.current_casts || [])) {
      if (typeof c.cast_id === 'number') castOnOtherTable[c.cast_id] = t.table_no || `#${t.id}`
    }
  }

  const casts = (castsAll as any[]).filter((c: any) => c.is_active && workingCastIds.has(c.id))
  const filtered = casts.filter((c: any) => !q || c.stage_name?.includes(q))

  const toggle = (cid: number) => {
    if (selected.includes(cid)) {
      setSelected(selected.filter(x => x !== cid))
      return
    }
    const otherTable = castOnOtherTable[cid]
    if (otherTable) {
      if (!confirm(`${otherTable} で対応中です。\nこの卓に移しますか？`)) return
    }
    setSelected([...selected, cid])
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={e => { e.stopPropagation(); onClose() }}>
      <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">対応中キャストを設定</h3>
          <button onClick={e => { e.stopPropagation(); onClose() }}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <input type="text" value={q} onChange={e => setQ(e.target.value)}
          placeholder="キャスト名で検索"
          className="input-field w-full text-sm" autoFocus />
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {filtered.map((c: any) => {
            const isSelected = selected.includes(c.id)
            const otherTable = castOnOtherTable[c.id]
            return (
              <button key={c.id} onClick={e => { e.stopPropagation(); toggle(c.id) }}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${isSelected ? 'bg-primary-700 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-200'}`}>
                <span className="font-medium flex items-center gap-2">
                  <span className={`inline-block w-3.5 h-3.5 border rounded ${isSelected ? 'bg-white border-white' : 'border-gray-500'}`}>
                    {isSelected && <span className="block w-full h-full text-primary-700 text-[10px] leading-3 text-center">✓</span>}
                  </span>
                  {c.stage_name}
                </span>
                {otherTable && !isSelected && (
                  <span className="text-[10px] text-amber-400">{otherTable} 対応中</span>
                )}
              </button>
            )
          })}
          {filtered.length === 0 && <p className="text-center text-gray-500 text-sm py-4">出勤中キャストがいません</p>}
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={e => { e.stopPropagation(); setSelected([]) }}
            className="text-xs px-3 py-1.5 text-gray-400 hover:text-gray-200">全解除</button>
          <button onClick={e => { e.stopPropagation(); onSubmit(selected); onClose() }}
            className="text-xs px-4 py-1.5 bg-primary-700 hover:bg-primary-600 text-white rounded-lg">
            確定（{selected.length}名）
          </button>
        </div>
      </div>
    </div>
  )
}

function ChampagneMenuModal({ onSelect, onClose }: {
  onSelect: (name: string, price: number) => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4" onClick={e => { e.stopPropagation(); onClose() }}>
      <div className="card w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-bold text-white">シャンパン選択</h3>
          <button onClick={e => { e.stopPropagation(); onClose() }}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-1.5 max-h-[70vh] overflow-y-auto pr-1">
          {CHAMPAGNE_MENU.map(({ name, price }) => (
            <button key={name} onClick={e => { e.stopPropagation(); onSelect(name, price) }}
              className="w-full flex justify-between items-center px-3 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors">
              <span className="text-gray-200">{name}</span>
              <span className="text-pink-400 font-medium">¥{price.toLocaleString()}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// キャスト選択が必要な注文ボタンを押したときのモーダル
// シャンパンのみ複数キャスト選択可（キャストごとに1件ずつ追加）
function CastSelectModal({ itemType, itemLabel, storeId, onSubmit, onClose }: {
  itemType: string
  itemLabel: string
  storeId: number
  onSubmit: (selections: { castId: number; castName: string; ratio: number }[]) => void
  onClose: () => void
}) {
  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const { data: workingAttendance = [] } = useQuery({
    queryKey: ['attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/attendance/working/${storeId}`).then(r => r.data),
    staleTime: 30000,
  })
  const workingCastIds = new Set(
    (workingAttendance as any[])
      .filter((a: any) => a.cast_id != null && !a.actual_end && !a.is_absent)
      .map((a: any) => a.cast_id)
  )
  const casts = (castsAll as any[]).filter((c: any) => c.is_active && workingCastIds.has(c.id))
  const isChampagne = itemType === 'champagne'

  // 単一選択
  const [castId, setCastId] = useState<number | null>(null)
  // 複数選択＋割合（シャンパン）
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [ratios, setRatios] = useState<Record<number, number>>({}) // castId -> %(10,20,...,100)

  const redistributeRatios = (ids: Set<number>) => {
    const arr = Array.from(ids)
    if (arr.length === 0) { setRatios({}); return }
    const base = Math.floor(100 / arr.length)
    const remainder = 100 - base * arr.length
    const newRatios: Record<number, number> = {}
    arr.forEach((id, i) => { newRatios[id] = base + (i === 0 ? remainder : 0) })
    setRatios(newRatios)
  }

  const toggleCast = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      redistributeRatios(next)
      return next
    })
  }

  const totalRatio = isChampagne ? Array.from(selectedIds).reduce((sum, id) => sum + (ratios[id] || 10), 0) : 0
  const ratioOver = isChampagne && totalRatio > 100
  const canSubmit = isChampagne ? selectedIds.size > 0 && !ratioOver : castId !== null

  const handleSubmit = () => {
    if (isChampagne) {
      const selections = casts
        .filter((c: any) => selectedIds.has(c.id))
        .map((c: any) => ({ castId: c.id, castName: c.stage_name, ratio: ratios[c.id] || 10 }))
      onSubmit(selections)
    } else {
      const cast = casts.find((c: any) => c.id === castId)
      if (cast) onSubmit([{ castId: cast.id, castName: cast.stage_name, ratio: 100 }])
    }
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4">
      <div className="card w-full max-w-xs space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">{itemLabel} — キャスト選択{isChampagne && <span className="text-xs text-gray-400 font-normal ml-1">（複数可）</span>}</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        {isChampagne ? (
          <div className="space-y-1.5 max-h-[55vh] overflow-y-auto">
            {casts.map((c: any) => (
              <div key={c.id} className="flex items-center gap-2">
                <button onClick={() => toggleCast(c.id)}
                  className={`flex-1 text-left px-3 py-2 rounded-lg text-sm transition-colors ${selectedIds.has(c.id) ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-300 hover:bg-night-600'}`}>
                  {c.stage_name}
                </button>
                {selectedIds.has(c.id) && (
                  <div className="flex items-center gap-1 shrink-0">
                    <input type="number" min={1} max={100} value={ratios[c.id] ?? 10}
                      onChange={e => setRatios(r => ({ ...r, [c.id]: Math.min(100, Math.max(1, Number(e.target.value))) }))}
                      className="input-field text-sm w-16 text-center" />
                    <span className="text-gray-400 text-sm">%</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-1 max-h-[55vh] overflow-y-auto">
            {casts.map((c: any) => (
              <button key={c.id} onClick={() => setCastId(c.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${castId === c.id ? 'bg-primary-700 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-200'}`}>
                <span className="font-medium">{c.stage_name}</span>
              </button>
            ))}
            {casts.length === 0 && <p className="text-center text-gray-500 text-sm py-4">勤務中のキャストがいません</p>}
          </div>
        )}
        {isChampagne && selectedIds.size > 0 && (
          <div className={`text-sm text-center font-bold ${ratioOver ? 'text-red-400' : 'text-gray-400'}`}>
            合計: {totalRatio}% {ratioOver && '（100%を超えています）'}
          </div>
        )}
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={handleSubmit} disabled={!canSubmit} className="btn-primary flex-1 disabled:opacity-40">追加</button>
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
  const [showChampagneMenu, setShowChampagneMenu] = useState(false)
  const [showOtherInput, setShowOtherInput] = useState(false)
  const [otherName, setOtherName] = useState('')
  const [otherPrice, setOtherPrice] = useState('')
  const [editingStartTime, setEditingStartTime] = useState(false)
  const [editStartHour, setEditStartHour] = useState(0)
  const [editStartMin, setEditStartMin] = useState(0)
  const [timeChangeOperator, setTimeChangeOperator] = useState('')
  const [timeChangeReason, setTimeChangeReason] = useState('')
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null)
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null)
  const [editingQty, setEditingQty] = useState(1)
  const [actionMode, setActionMode] = useState<'add' | 'delete' | 'edit'>('add')
  const [editingGroupMaxQty, setEditingGroupMaxQty] = useState(1)
  const [editingGroupItemIds, setEditingGroupItemIds] = useState<number[]>([])
  const [operatorName, setOperatorName] = useState('')
  const [operatorReason, setOperatorReason] = useState('')
  const [champEditCasts, setChampEditCasts] = useState<{ castId: number | null; castName: string; ratio: number }[]>([])
  const [actionPos, setActionPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const [showCustomerSearch, setShowCustomerSearch] = useState(false)
  const [showCastSearch, setShowCastSearch] = useState(false)
  const [showActiveCastsModal, setShowActiveCastsModal] = useState(false)
  const [showJoinModal, setShowJoinModal] = useState(false)
  const [showReceiptModal, setShowReceiptModal] = useState(false)
  const [receiptHistory, setReceiptHistory] = useState<any[]>([])
  const [receiptRecipient, setReceiptRecipient] = useState('')
  const [receiptPaperSize, setReceiptPaperSize] = useState<'80mm' | 'a4'>('80mm')
  const [receiptIssuing, setReceiptIssuing] = useState(false)
  const [showMergeModal, setShowMergeModal] = useState(false)
  const [showWarikanModal, setShowWarikanModal] = useState(false)
  const [showSenkaikeiModal, setShowSenkaikeiModal] = useState(false)
  const [showSentaitenModal, setShowSentaitenModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [showDiscountModal, setShowDiscountModal] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null)
  const [showHeaderEdit, setShowHeaderEdit] = useState(false)
  const [headerEditForm, setHeaderEditForm] = useState<{ table_no: string; guest_count: number; visit_type: string; plan_type: string; visit_motivation: string; motivation_cast_id: number | null }>({ table_no: '', guest_count: 1, visit_type: '', plan_type: 'standard', visit_motivation: '', motivation_cast_id: null })
  const [headerEditOperator, setHeaderEditOperator] = useState('')
  const [headerEditError, setHeaderEditError] = useState('')

  const confirmCheckout = (fn: () => void) => setPendingAction(() => fn)

  const { data: ticket, isLoading } = useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => apiClient.get(`/api/tickets/${ticketId}`).then(r => r.data),
    staleTime: 0,
    refetchInterval: (query) => (query.state.data?.is_closed ? false : 10000),
  })

  // 横断キャスト最新ドリンク用（オープン中伝票）
  const { data: openTicketsForTimers = [] } = useQuery({
    queryKey: ['tickets', storeId, 'open'],
    queryFn: () => apiClient.get('/api/tickets', { params: { store_id: storeId, is_closed: false } }).then(r => r.data),
    staleTime: 5000,
    enabled: !!storeId,
  })
  const detailCastLatestMap = useMemo(() => {
    const out: Record<number, { ticketId: number; lastAt: string }> = {}
    for (const t of (openTicketsForTimers as any[])) {
      const ldt = t.last_drink_times || {}
      for (const [type, arr] of Object.entries(ldt) as any[]) {
        if (type === 'champagne') continue
        if (!Array.isArray(arr)) continue
        for (const c of arr) {
          if (!c || c.cast_id == null || !c.last_at) continue
          const cur = out[c.cast_id]
          if (!cur || c.last_at > cur.lastAt) out[c.cast_id] = { ticketId: t.id, lastAt: c.last_at }
        }
      }
    }
    return out
  }, [openTicketsForTimers])

  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const castMap: Record<number, string> = Object.fromEntries(
    (castsAll as any[]).map((c: any) => [c.id, c.stage_name])
  )

  const { data: customMenuItems = [] } = useQuery({
    queryKey: ['menu-items', storeId],
    queryFn: () => apiClient.get('/api/app-settings/menu', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
  })
  const activeMenuItems = (customMenuItems as any[]).filter((m: any) => m.is_active)

  const addOrderMutation = useMutation({
    mutationFn: (item: { item_type: string; unit_price: number; quantity: number; cast_id?: number | null; item_name?: string }) => {
      // キャスト選択ありのドリンク系（タイマー対象）は新規行追加にする
      // → 追加注文時に created_at を更新してドリンクタイマーをリセットする
      const isCastDrink = CAST_SELECT_TYPES.has(item.item_type) || item.item_type === 'custom_menu'
      if (isCastDrink && item.cast_id != null) {
        return apiClient.post(`/api/tickets/${ticketId}/orders`, item).then(r => r.data)
      }
      // キャッシュから最新データを取得（クロージャのticketは更新が遅延する場合があるため）
      const latestTicket = qc.getQueryData<any>(['ticket', ticketId])
      const orderItems = (latestTicket?.order_items ?? []) as any[]
      const targetName = item.item_name ?? null
      const targetCastId = item.cast_id ?? null
      const existing = orderItems.find((oi: any) =>
        !oi.canceled_at &&
        oi.item_type === item.item_type &&
        (oi.item_name ?? null) === targetName &&
        (oi.cast_id ?? null) === targetCastId
      )
      if (existing) {
        const newQty = existing.quantity + item.quantity
        // 即時キャッシュ更新で次の追加も重複しない
        qc.setQueryData(['ticket', ticketId], (old: any) => old ? {
          ...old,
          order_items: old.order_items.map((oi: any) =>
            oi.id === existing.id ? { ...oi, quantity: newQty, amount: oi.unit_price * newQty } : oi
          )
        } : old)
        return apiClient.patch(`/api/tickets/orders/${existing.id}`, { quantity: newQty }).then(r => r.data)
      }
      return apiClient.post(`/api/tickets/${ticketId}/orders`, item).then(r => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
    },
  })

  const cancelOrderMutation = useMutation({
    mutationFn: ({ itemId, operator, reason }: { itemId: number; operator: string; reason: string }) =>
      apiClient.post(`/api/tickets/orders/${itemId}/cancel`, { operator_name: operator || null, reason: reason || null }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      qc.invalidateQueries({ queryKey: ['order-logs', storeId] })
      setSelectedOrderId(null)
      setOperatorName('')
      setOperatorReason('')
    },
  })

  const updateOrderMutation = useMutation({
    mutationFn: ({ itemId, quantity, operator, reason }: { itemId: number; quantity: number; operator: string; reason: string }) =>
      apiClient.patch(`/api/tickets/orders/${itemId}`, { quantity, operator_name: operator || null, reason: reason || null }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      qc.invalidateQueries({ queryKey: ['order-logs', storeId] })
      setEditingOrderId(null)
      setSelectedOrderId(null)
      setOperatorName('')
      setOperatorReason('')
    },
  })

  const updateChampagneMutation = useMutation({
    mutationFn: ({ oldName, newName, operator, reason, distribution }: { oldName: string; newName: string; operator: string; reason: string; distribution?: { cast_id: number; ratio: number }[] }) =>
      apiClient.patch(`/api/tickets/${ticketId}/update-champagne`, {
        old_item_name: oldName,
        new_item_name: newName,
        operator_name: operator || null,
        reason: reason || null,
        cast_distribution: distribution || null,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      qc.invalidateQueries({ queryKey: ['order-logs', storeId] })
      qc.invalidateQueries({ queryKey: ['daily-report', storeId] })
      setEditingOrderId(null)
      setSelectedOrderId(null)
      setActionPos(null)
      setOperatorName('')
      setOperatorReason('')
      setActionMode('add')
      setChampEditCasts([])
    },
    onError: (e: any) => {
      const detail = e?.response?.data?.detail || e?.message || '保存に失敗しました'
      alert(`シャンパン分配の保存に失敗しました\n${detail}`)
    },
  })

  const patchHeaderMutation = useMutation({
    mutationFn: (payload: any) =>
      apiClient.patch(`/api/tickets/${ticketId}`, payload).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
      setShowHeaderEdit(false)
      setHeaderEditOperator('')
      setHeaderEditError('')
    },
    onError: (e: any) => {
      setHeaderEditError(e.response?.data?.detail || '保存に失敗しました')
    },
  })

  // グループ編集: バックエンドで一括アトミック処理
  const groupReduceMutation = useMutation({
    mutationFn: ({ item, targetQty, operator, reason }: { item: any; targetQty: number; operator: string; reason: string }) =>
      apiClient.post(`/api/tickets/${ticketId}/reduce-group`, {
        item_type: item.item_type,
        item_name: item.item_name ?? null,
        unit_price: item.unit_price,
        target_quantity: targetQty,
        operator_name: operator || null,
        reason: reason || null,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      qc.invalidateQueries({ queryKey: ['order-logs', storeId] })
      setEditingOrderId(null)
      setSelectedOrderId(null)
      setOperatorName('')
      setOperatorReason('')
    },
  })

  const closeMutation = useMutation({
    mutationFn: (data: any) => apiClient.post(`/api/tickets/${ticketId}/close`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      onClose()
    },
  })

  const setStartMutation = useMutation({
    mutationFn: () => apiClient.post(`/api/tickets/${ticketId}/set-start`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ticket', ticketId] }),
  })

  const setToggleMutation = useMutation({
    mutationFn: () => apiClient.post(`/api/tickets/${ticketId}/set-toggle`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ticket', ticketId] }),
  })

  const setCustomerMutation = useMutation({
    mutationFn: (customerId: number | null) =>
      apiClient.post(`/api/tickets/${ticketId}/set-customer`, { customer_id: customerId }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      setShowCustomerSearch(false)
    },
  })

  const setCastMutation = useMutation({
    mutationFn: (castId: number | null) =>
      apiClient.post(`/api/tickets/${ticketId}/set-cast`, { cast_id: castId }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      setShowCastSearch(false)
    },
  })

  const setActiveCastsMutation = useMutation({
    mutationFn: (castIds: number[]) =>
      apiClient.post(`/api/tickets/${ticketId}/assignments/set`, { cast_ids: castIds }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      setShowActiveCastsModal(false)
    },
  })

  const joinMutation = useMutation({
    mutationFn: (data: any) => apiClient.post(`/api/tickets/${ticketId}/join`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      setShowJoinModal(false)
    },
  })

  const mergeMutation = useMutation({
    mutationFn: (targetId: number) =>
      apiClient.post(`/api/tickets/${ticketId}/merge`, { target_ticket_id: targetId }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickets', storeId] })
      onClose()
    },
  })

  const handleItemClick = (type: string, label: string, price: number) => {
    if (type === 'other') {
      setShowOtherInput(v => !v)
    } else if (type === 'champagne') {
      setShowChampagneMenu(true)
    } else if (CAST_SELECT_TYPES.has(type)) {
      setCastSelectItem({ type, label, price })
    } else {
      addOrderMutation.mutate({ item_type: type, unit_price: price, quantity: 1 })
    }
  }

  const handleOtherAdd = () => {
    const price = parseInt(otherPrice, 10)
    if (!otherPrice || isNaN(price) || price <= 0) return
    addOrderMutation.mutate({ item_type: 'other', item_name: otherName || 'その他', unit_price: price, quantity: 1 })
    setOtherName('')
    setOtherPrice('')
    setShowOtherInput(false)
  }

  const fetchAI = async () => {
    setLoadingAI(true)
    try {
      const res = await apiClient.post(`/api/ai/suggest-rotation/${storeId}`)
      const data = res.data
      // この伝票の提案だけ抽出
      const mySuggestion = (data.suggestions || []).find((s: any) => s.ticket_id === ticketId)
      let text = ''
      if (mySuggestion && mySuggestion.recommended_casts?.length) {
        text = mySuggestion.recommended_casts
          .map((c: any, i: number) => `${i + 1}位 ${c.stage_name}（${c.score}点）\n  ${c.reason}`)
          .join('\n\n')
      } else {
        text = 'この卓への推薦は見つかりませんでした'
      }
      if (data.overall_advice) text += `\n\n💡 ${data.overall_advice}`
      setAiAdvice(text)
    } catch (e: any) {
      setAiAdvice(e?.response?.data?.detail || 'AIアドバイスを取得できませんでした')
    }
    setLoadingAI(false)
  }

  if (isLoading || !ticket) return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="text-gray-400">読み込み中...</div>
    </div>
  )

  const isClosed = !!ticket.is_closed
  // クローズ済みは ended_at を基準に固定、オープン中は now でカウント
  const refTime = isClosed ? (toUtcMs(ticket.ended_at) ?? now) : now
  const elapsed = calcElapsed(ticket.set_started_at || ticket.started_at, refTime)
  const setElapsed = isClosed ? null : calcSetElapsed(ticket, now)
  const eElapsed = ticket.e_started_at ? calcElapsed(ticket.e_started_at, refTime) : null
  const startedAtMs = toUtcMs(ticket.started_at)
  const startedAt = startedAtMs ? new Date(startedAtMs) : new Date()

  // 先会計: 小計には含めず、合計（税サ込み）からのみ差し引く
  const senkaikeiTotal = (ticket.order_items || [])
    .filter((i: any) => (i.item_name?.startsWith('先会計') || i.item_name?.startsWith('分割清算') || i.item_name?.startsWith('値引き')) && !i.canceled_at)
    .reduce((s: number, i: any) => s + Math.abs(i.amount), 0)
  const subtotal = ticket.total_amount + senkaikeiTotal
  const grandTotal = Math.round(subtotal * 1.21) - senkaikeiTotal

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-2 sm:p-4">
      <div className="bg-night-800 border border-night-600 rounded-2xl w-full max-w-4xl h-[92vh] flex flex-col overflow-hidden">

        {/* ヘッダー */}
        <div className="px-4 py-3 border-b border-night-600 shrink-0 space-y-2">
          <div className="flex justify-between items-center">
            {(() => {
              const openHeader = () => {
                setHeaderEditForm({
                  table_no: ticket.table_no || '',
                  guest_count: ticket.guest_count || 1,
                  visit_type: ticket.visit_type || '',
                  plan_type: ticket.plan_type || 'standard',
                  visit_motivation: ticket.visit_motivation || '',
                  motivation_cast_id: ticket.motivation_cast_id || null,
                })
                setHeaderEditError('')
                setShowHeaderEdit(true)
              }
              const clickable = !isClosed
              return (
                <div className="flex items-center gap-3">
                  <button
                    disabled={!clickable}
                    onClick={openHeader}
                    className={`text-xl font-bold text-white ${clickable ? 'hover:text-primary-300 transition-colors' : ''}`}
                  >{ticket.table_no || '—'}</button>
                  <div className="flex gap-1.5 flex-wrap">
                    <button
                      disabled={!clickable}
                      onClick={openHeader}
                      className={`badge text-xs ${ticket.visit_type === 'N' ? 'bg-blue-900/40 text-blue-400' : ticket.visit_type === 'R' ? 'bg-purple-900/40 text-purple-400' : 'bg-night-700 text-gray-500'} ${clickable ? 'hover:opacity-80' : ''}`}
                    >{ticket.visit_type || 'N/R'}</button>
                    <button
                      disabled={!clickable}
                      onClick={openHeader}
                      className={`badge text-xs ${ticket.plan_type === 'premium' ? 'bg-yellow-900/40 text-yellow-400' : 'bg-gray-700 text-gray-300'} ${clickable ? 'hover:opacity-80' : ''}`}
                    >{ticket.plan_type === 'premium' ? 'プレミアム' : 'スタンダード'}</button>
                    <button
                      disabled={!clickable}
                      onClick={openHeader}
                      className={`badge text-xs bg-night-600 text-gray-300 ${clickable ? 'hover:opacity-80' : ''}`}
                    >{ticket.guest_count || 1}名様</button>
                    {ticket.visit_motivation && (
                      <button
                        disabled={!clickable}
                        onClick={openHeader}
                        className={`badge text-xs bg-teal-900/40 text-teal-400 ${clickable ? 'hover:opacity-80' : ''}`}
                      >
                        {ticket.visit_motivation}
                        {ticket.motivation_cast_name && `／${ticket.motivation_cast_name}`}
                        {ticket.motivation_note && `／${ticket.motivation_note}`}
                      </button>
                    )}
                  </div>
                </div>
              )
            })()}
            <div className="flex items-center gap-2">
              <button onClick={() => setShowDeleteModal(true)}
                className="text-xs px-3 py-1.5 bg-red-900/60 hover:bg-red-800/70 text-red-300 rounded-lg transition-colors">
                削除
              </button>
              {!isClosed && (
                <>
                  <button onClick={() => setShowSentaitenModal(true)}
                    className="text-xs px-3 py-1.5 bg-orange-900/60 hover:bg-orange-800/70 text-orange-300 rounded-lg transition-colors">
                    先退店
                  </button>
                  <button onClick={() => setShowMergeModal(true)}
                    className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors">
                    合算
                  </button>
                  <button onClick={() => setShowSenkaikeiModal(true)}
                    className="text-xs px-3 py-1.5 bg-blue-900/60 hover:bg-blue-800/70 text-blue-300 rounded-lg transition-colors">
                    先会計
                  </button>
                  <button onClick={() => setShowWarikanModal(true)}
                    className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors">
                    割り勘
                  </button>
                </>
              )}
              <p className="text-xl font-bold text-primary-400 ml-2">¥{grandTotal.toLocaleString()}</p>
              <button
                onClick={() => setShowLog(true)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-gray-500 rounded-lg px-2 py-1 transition-colors"
              >
                <ClipboardList className="w-3.5 h-3.5" />ログ
              </button>
              <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
            </div>
          </div>

          {/* タイマー行 */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <div className="flex gap-2 text-xs">
              {!isClosed ? (
                <>
                  <button onClick={() => setShowCustomerSearch(true)}
                    className="text-gray-400 hover:text-white underline decoration-dotted transition-colors">
                    {ticket.customer_name || '顧客未設定'}
                  </button>
                  <span className="text-gray-600">/</span>
                  <button onClick={() => setShowCastSearch(true)}
                    className="text-primary-400 hover:text-primary-300 underline decoration-dotted transition-colors">
                    {ticket.featured_cast_name || '担当未設定'}
                  </button>
                  <span className="text-gray-600">/</span>
                  <button onClick={() => setShowActiveCastsModal(true)}
                    className="text-purple-300 hover:text-purple-200 underline decoration-dotted transition-colors">
                    {(ticket.current_casts && ticket.current_casts.length > 0)
                      ? `対応中: ${ticket.current_casts.map((c: any) => c.cast_name).join('・')}`
                      : '対応中未設定'}
                  </button>
                </>
              ) : (
                <>
                  <span className="text-gray-400">{ticket.customer_name || '顧客未設定'}</span>
                  <span className="text-gray-600">/</span>
                  <span className="text-primary-400">{ticket.featured_cast_name || '担当未設定'}</span>
                  <span className="text-gray-600">/</span>
                  <span className="text-purple-300">
                    {(ticket.current_casts && ticket.current_casts.length > 0)
                      ? `対応中: ${ticket.current_casts.map((c: any) => c.cast_name).join('・')}`
                      : '対応中未設定'}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center gap-1 font-mono text-sm">
              <span className="text-gray-500 text-xs">経過</span>
              <span className="text-green-400">{fmtTime(elapsed)}</span>
            </div>
            {eElapsed !== null && (
              <div className="flex items-center gap-1 font-mono text-sm">
                <span className="text-gray-500 text-xs">E</span>
                <span className="text-orange-400">{fmtTime(eElapsed)}</span>
              </div>
            )}
            {isClosed && ticket.ended_at && (() => {
              const endMs = toUtcMs(ticket.ended_at)
              const endDate = endMs ? new Date(endMs) : null
              return endDate ? (
                <span className="text-xs text-gray-500 ml-auto">
                  {toBarHour(endDate.getHours()).toString().padStart(2,'0')}:{endDate.getMinutes().toString().padStart(2,'0')} 退店
                  <span className="ml-2 text-green-600">{PAYMENT_LABELS[ticket.payment_method] ?? ''}</span>
                </span>
              ) : null
            })()}

            {/* セットタイマー（オープン中のみ） */}
            {!isClosed && (
              <div className="flex items-center gap-2 ml-auto">
                {!ticket.set_started_at ? (
                  <button onClick={() => setStartMutation.mutate()} disabled={setStartMutation.isPending}
                    className="flex items-center gap-2 px-5 py-2 bg-green-700 hover:bg-green-600 text-white rounded-xl text-sm font-bold transition-colors disabled:opacity-50">
                    <Play className="w-4 h-4" />伝票開始
                  </button>
                ) : (
                  <>
                    {(() => {
                      const countdown = calcSetCountdown(setElapsed)
                      const urgent = countdown !== null && countdown <= 5 * 60
                      const intervalNum = calcSetInterval(setElapsed)
                      const nowMs = Date.now()
                      const joinItems = (ticket.order_items || []).filter((i: any) =>
                        i.item_name && i.item_name.includes('合流') && i.created_at
                      )
                      return (
                        <>
                          {joinItems.map((item: any) => {
                            const startMs = new Date(item.created_at.endsWith('Z') ? item.created_at : item.created_at + 'Z').getTime()
                            const elapsed = nowMs - startMs
                            const remaining = JOIN_DURATION - (elapsed % JOIN_DURATION)
                            const joinUrgent = remaining <= 5 * 60 * 1000
                            return (
                              <span key={item.id} className="flex items-center gap-1">
                                <span className="text-xs text-gray-500">合流</span>
                                <span className={`text-lg font-bold font-mono ${joinUrgent ? 'text-red-400' : 'text-blue-400'}`}>{fmtTime(Math.floor(remaining / 1000))}</span>
                              </span>
                            )
                          })}
                          <span className="text-xs text-gray-500">セット残り</span>
                          <span className={`text-lg font-bold font-mono ${ticket.set_is_paused ? 'text-yellow-400' : urgent ? 'text-red-400' : 'text-green-400'}`}>
                            {countdown !== null ? fmtTime(countdown) : '—'}
                          </span>
                          {intervalNum > 0 && <span className="badge bg-night-700 text-gray-400 text-xs">{intervalNum}延長済</span>}
                        </>
                      )
                    })()}
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
            )}
          </div>

          {/* D時間（オープン中のみ） */}
          {!isClosed && (
            <DrinkTimers lastDrinkTimes={ticket.last_drink_times} now={now} ticketId={ticketId}
              castLatestMap={detailCastLatestMap}
              currentCastIds={(ticket.current_casts || []).map((c: any) => c.cast_id).filter((id: any) => id != null)}
              onCleared={() => { qc.invalidateQueries({ queryKey: ['ticket', ticketId] }); qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] }) }}
              onCastRemove={(castId) => {
                const remaining = (ticket.current_casts || []).map((c: any) => c.cast_id).filter((id: any) => id != null && id !== castId)
                apiClient.post(`/api/tickets/${ticketId}/assignments/set`, { cast_ids: remaining }).then(() => {
                  qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
                  qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
                })
              }} />
          )}
        </div>

        {/* 本体: 左(伝票) + 右(操作) */}
        <div className="flex flex-1 overflow-hidden">
          {/* 左: 伝票（クローズ済みは全幅） */}
          <div className={`${isClosed ? 'w-1/2 border-r border-night-600' : 'w-1/2 border-r border-night-600'} flex flex-col overflow-hidden`}>
            <div className="px-4 py-2 border-b border-night-700">
              {editingStartTime ? (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1">
                    <select value={editStartHour} onChange={e => setEditStartHour(Number(e.target.value))} className="input-field text-xs py-0.5 px-1 w-16">
                      {!BAR_HOURS.includes(editStartHour) && (
                        <option value={editStartHour}>{String(editStartHour).padStart(2,'0')}</option>
                      )}
                      {BAR_HOURS.map(n => <option key={n} value={n}>{String(n).padStart(2,'0')}</option>)}
                    </select>
                    <span className="text-gray-500 text-xs">:</span>
                    <select value={editStartMin} onChange={e => setEditStartMin(Number(e.target.value))} className="input-field text-xs py-0.5 px-1 w-14">
                      {Array.from({ length: 60 }, (_, i) => <option key={i} value={i}>{i.toString().padStart(2,'0')}</option>)}
                    </select>
                  </div>
                  <input type="text" placeholder="担当者名（必須）" value={timeChangeOperator}
                    onChange={e => setTimeChangeOperator(e.target.value)}
                    className="input-field w-full text-xs py-0.5" />
                  <input type="text" placeholder="理由（任意）" value={timeChangeReason}
                    onChange={e => setTimeChangeReason(e.target.value)}
                    className="input-field w-full text-xs py-0.5" />
                  <div className="flex gap-1">
                    <button
                      disabled={!timeChangeOperator.trim()}
                      onClick={() => {
                        const base = new Date(startedAt)
                        base.setHours(fromBarHour(editStartHour), editStartMin, 0, 0)
                        const utcIso = base.toISOString()
                        apiClient.patch(`/api/tickets/${ticketId}`, {
                          started_at: utcIso,
                          operator_name: timeChangeOperator || null,
                          reason: timeChangeReason || null,
                        }).then(() => {
                          qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
                          qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
                          qc.invalidateQueries({ queryKey: ['order-logs', storeId] })
                        })
                        setEditingStartTime(false)
                        setTimeChangeOperator('')
                        setTimeChangeReason('')
                      }}
                      className="text-xs bg-primary-600 hover:bg-primary-500 text-white px-2 py-0.5 rounded disabled:opacity-40">保存</button>
                    <button onClick={() => { setEditingStartTime(false); setTimeChangeOperator(''); setTimeChangeReason('') }}
                      className="text-xs text-gray-500">×</button>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 inline-flex items-center gap-1"
                  onClick={() => { setEditStartHour(toBarHour(startedAt.getHours())); setEditStartMin(startedAt.getMinutes()); setEditingStartTime(true) }}>
                  {toBarHour(startedAt.getHours()).toString().padStart(2,'0')}:{startedAt.getMinutes().toString().padStart(2,'0')} 入店
                  <span className="text-primary-500 text-xs">✎</span>
                </p>
              )}
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
                  {(() => {
                    // 同一品目（同item_type・同item_name・同unit_price）の未キャンセル行をまとめて表示
                    const raw = (ticket.order_items || []).filter((i: any) => !(i.item_type === 'champagne' && i.unit_price === 0))
                    const grouped: any[] = []
                    for (const item of raw) {
                      if (item.canceled_at) { grouped.push(item); continue }
                      const canMerge = item.item_type !== 'join' && item.item_type !== 'set'
                        && !item.item_name?.startsWith('先会計') && !item.item_name?.startsWith('分割清算') && !item.item_name?.startsWith('先退店') && !item.item_name?.startsWith('値引き')
                      if (canMerge) {
                        const key = `${item.item_type}|${item.item_name ?? ''}|${item.unit_price}`
                        const existing = grouped.find((g: any) => !g.canceled_at && g._groupKey === key)
                        if (existing) { existing.quantity += item.quantity; existing.amount += item.amount; continue }
                        grouped.push({ ...item, _groupKey: key })
                      } else {
                        grouped.push(item)
                      }
                    }
                    return grouped
                  })().map((item: any) => {
                    const isCanceled = !!item.canceled_at
                    const isSelected = selectedOrderId === item.id
                    const isEditing = editingOrderId === item.id
                    return (
                      <tr key={item.id}
                        className={`border-b border-night-700/50 ${!isCanceled ? 'cursor-pointer hover:bg-night-700/30' : ''} ${isSelected ? 'bg-night-700/50' : ''}`}
                        onClick={e => {
                          if (isCanceled) return
                          if (isEditing) return
                          if (isSelected) {
                            setSelectedOrderId(null)
                            setEditingOrderId(null)
                            setActionPos(null)
                          } else {
                            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
                            setActionPos({ top: rect.bottom, left: rect.left, width: rect.width })
                            setSelectedOrderId(item.id)
                            setEditingOrderId(null)
                            setActionMode('add')
                            setOperatorName('')
                          }
                        }}>
                        <td className={`px-4 py-2 ${isCanceled ? 'line-through text-gray-500' : 'text-gray-200'}`}>{displayItemName(item, castMap)}</td>
                        <td className={`text-center px-2 py-2 ${isCanceled ? 'line-through text-gray-600' : 'text-gray-400'}`}>
                          {item.quantity}
                        </td>
                        <td className={`text-right px-2 py-2 ${isCanceled ? 'text-gray-600' : 'text-gray-400'}`}>¥{item.unit_price.toLocaleString()}</td>
                        <td className={`text-right px-4 py-2 font-medium ${isCanceled ? 'line-through text-gray-600' : (item.item_name?.startsWith('先会計') || item.item_name?.startsWith('分割清算')) ? 'text-blue-400' : item.item_name?.startsWith('値引き') ? 'text-orange-400' : 'text-white'}`}>
                          {(item.item_name?.startsWith('先会計') || item.item_name?.startsWith('分割清算') || item.item_name?.startsWith('値引き')) ? `-¥${Math.abs(item.amount).toLocaleString()}` : `¥${item.amount.toLocaleString()}`}
                        </td>
                      </tr>
                    )
                  })}
                  {(!ticket.order_items || ticket.order_items.filter((i: any) => !(i.item_type === 'champagne' && i.unit_price === 0) && !i.canceled_at).length === 0) && (
                    <tr><td colSpan={4} className="text-center text-gray-600 py-8 text-sm">注文なし</td></tr>
                  )}
                </tbody>
              </table>
            </div>


            <div className="border-t border-night-600 px-4 py-3 space-y-1 shrink-0">
              <div className="flex justify-between items-center">
                <span className="text-gray-500 text-xs">小計</span>
                <span className="text-gray-400 text-sm">¥{subtotal.toLocaleString()}</span>
              </div>
              {(() => {
                const senkaikei = (ticket.order_items || []).filter((i: any) => (i.item_name?.startsWith('先会計') || i.item_name?.startsWith('分割清算')) && !i.canceled_at).reduce((s: number, i: any) => s + Math.abs(i.amount), 0)
                const discount  = (ticket.order_items || []).filter((i: any) => i.item_name?.startsWith('値引き') && !i.canceled_at).reduce((s: number, i: any) => s + Math.abs(i.amount), 0)
                return <>
                  {senkaikei > 0 && (
                    <div className="flex justify-between items-center">
                      <span className="text-blue-400 text-xs">先会計</span>
                      <span className="text-blue-400 text-sm">-¥{senkaikei.toLocaleString()}</span>
                    </div>
                  )}
                  {discount > 0 && (
                    <div className="flex justify-between items-center">
                      <span className="text-orange-400 text-xs">値引き</span>
                      <span className="text-orange-400 text-sm">-¥{discount.toLocaleString()}</span>
                    </div>
                  )}
                </>
              })()}
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-xs">（サービス料10％／消費税10％）合計</span>
                {!isClosed ? (
                  <button onClick={() => setShowDiscountModal(true)}
                    className="text-primary-400 font-bold text-lg hover:text-primary-300 transition-colors active:scale-95">
                    ¥{grandTotal.toLocaleString()}
                  </button>
                ) : (
                  <span className="text-primary-400 font-bold text-lg">¥{grandTotal.toLocaleString()}</span>
                )}
              </div>
            </div>
          </div>

          {/* 右: 会計済み伝票では領収書発行のみ表示 */}
          {isClosed && (
            <div className="w-1/2 flex flex-col overflow-hidden border-l border-night-600">
              <div className="p-3 space-y-2">
                <p className="text-xs text-gray-500">印刷</p>
                <button
                  onClick={async () => {
                    try {
                      const r = await apiClient.get(`/api/receipts/estimate/${ticketId}?size=80mm`, { responseType: 'blob' })
                      window.open(URL.createObjectURL(r.data), '_blank')
                    } catch { alert('概算伝票の生成に失敗しました') }
                  }}
                  className="bg-blue-800 hover:bg-blue-700 text-white text-xs py-2 rounded-lg w-full"
                >🖨️ 概算伝票</button>
                <button
                  onClick={async () => {
                    setShowReceiptModal(true)
                    try {
                      const h = await apiClient.get(`/api/receipts/history/${ticketId}`)
                      setReceiptHistory(h.data)
                    } catch {}
                  }}
                  className="bg-emerald-800 hover:bg-emerald-700 text-white text-xs py-2 rounded-lg w-full"
                >📄 領収書発行</button>
              </div>
            </div>
          )}

          {/* 右: 操作（オープン中のみ） */}
          {!isClosed && <div className="w-1/2 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              <p className="text-xs text-gray-500 px-1">注文追加</p>
              <div className="grid grid-cols-2 gap-1">
                {ITEM_TYPES.map(({ type, label, defaultPrice }) => {
                  const price = type === 'extension'
                    ? (ticket.plan_type === 'premium' ? 4000 : 3000)
                    : defaultPrice
                  return (
                    <button key={type}
                      onClick={() => handleItemClick(type, label, price)}
                      className={`btn-secondary text-xs py-1.5 leading-tight ${CAST_SELECT_TYPES.has(type) ? 'border-primary-700/50' : ''}`}
                    >
                      {label}
                      {price > 0 && <span className="block text-[10px] text-gray-500">¥{price.toLocaleString()}</span>}
                      {CAST_SELECT_TYPES.has(type) && <span className="block text-[10px] text-primary-500">キャスト選択</span>}
                    </button>
                  )
                })}
                {activeMenuItems.map((m: any) => (
                  <button key={`menu-${m.id}`}
                    onClick={() => {
                      if (m.cast_required) {
                        setCastSelectItem({ type: 'custom_menu', label: m.label, price: m.price })
                      } else {
                        addOrderMutation.mutate({ item_type: 'other', item_name: m.label, unit_price: m.price, quantity: 1 })
                      }
                    }}
                    className={`btn-secondary text-xs py-1.5 leading-tight ${m.cast_required ? 'border-primary-700/50' : ''}`}
                  >
                    {m.label}
                    {m.price > 0 && <span className="block text-[10px] text-gray-500">¥{m.price.toLocaleString()}</span>}
                    {m.cast_required && <span className="block text-[10px] text-primary-500">キャスト選択</span>}
                  </button>
                ))}
              </div>

              {showOtherInput && (
                <div className="bg-night-700 rounded-lg p-3 space-y-2">
                  <p className="text-xs text-gray-400 font-medium">その他 — 詳細入力</p>
                  <input
                    type="text"
                    placeholder="品目名（任意）"
                    value={otherName}
                    onChange={e => setOtherName(e.target.value)}
                    className="input-field w-full text-sm"
                  />
                  <div className="flex gap-2">
                    <input
                      type="number"
                      placeholder="金額"
                      value={otherPrice}
                      onChange={e => setOtherPrice(e.target.value)}
                      className="input-field flex-1 text-sm"
                      min={1}
                    />
                    <button onClick={handleOtherAdd} disabled={!otherPrice || Number(otherPrice) <= 0}
                      className="btn-primary px-4 text-sm disabled:opacity-40">追加</button>
                  </div>
                </div>
              )}

              <div className="border-t border-night-700 pt-1.5">
                <button onClick={() => setShowJoinModal(true)}
                  className="btn-secondary w-full text-xs py-1.5">合流</button>
              </div>

              <div className="border-t border-night-700 pt-1.5 grid grid-cols-2 gap-2">
                <button
                  onClick={async () => {
                    try {
                      const r = await apiClient.get(`/api/receipts/estimate/${ticketId}?size=80mm`, { responseType: 'blob' })
                      const url = URL.createObjectURL(r.data)
                      window.open(url, '_blank')
                    } catch (e: any) {
                      alert('概算伝票の生成に失敗しました')
                    }
                  }}
                  className="bg-blue-800 hover:bg-blue-700 text-white text-xs py-1.5 rounded-lg"
                >
                  🖨️ 概算伝票
                </button>
                <button
                  onClick={async () => {
                    setShowReceiptModal(true)
                    try {
                      const h = await apiClient.get(`/api/receipts/history/${ticketId}`)
                      setReceiptHistory(h.data)
                    } catch {}
                  }}
                  className="bg-emerald-800 hover:bg-emerald-700 text-white text-xs py-1.5 rounded-lg"
                >
                  📄 領収書発行
                </button>
              </div>

              <div className="border-t border-night-700 pt-1.5">
                <button onClick={fetchAI} disabled={loadingAI}
                  className="flex items-center gap-1.5 text-primary-400 text-xs font-medium disabled:opacity-50">
                  <Bot className="w-3.5 h-3.5" />
                  {loadingAI ? 'AI分析中...' : '付け回しAIアドバイス'}
                </button>
                {aiAdvice && (
                  <div className="mt-2 p-3 bg-primary-900/20 border border-primary-800/40 rounded-xl text-xs text-gray-300 whitespace-pre-wrap">{aiAdvice}</div>
                )}
              </div>
            </div>

            <div className="border-t border-night-600 p-3 grid grid-cols-3 gap-2 shrink-0">
              <button onClick={() => confirmCheckout(() => closeMutation.mutate({ payment_method: 'cash', cash_amount: ticket.total_amount }))}
                className="btn-secondary flex items-center justify-center gap-1.5 py-3 text-sm">
                <Banknote className="w-4 h-4 shrink-0" />現金決済
              </button>
              <button onClick={() => confirmCheckout(() => closeMutation.mutate({ payment_method: 'card', card_amount: ticket.total_amount }))}
                className="btn-primary flex items-center justify-center gap-1.5 py-3 text-sm">
                <CreditCard className="w-4 h-4 shrink-0" />カード決済
              </button>
              <button onClick={() => confirmCheckout(() => closeMutation.mutate({ payment_method: 'code', code_amount: ticket.total_amount }))}
                className="bg-purple-700 hover:bg-purple-600 active:bg-purple-800 text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-1.5 py-3 text-sm">
                <QrCode className="w-4 h-4 shrink-0" />コード決済
              </button>
            </div>
          </div>}
        </div>
      </div>

      {/* 領収書発行モーダル */}
      {showReceiptModal && (
        <div className="fixed inset-0 bg-black/70 z-[200] flex items-center justify-center p-4" onClick={() => setShowReceiptModal(false)}>
          <div className="bg-night-900 border border-emerald-700/40 rounded-xl max-w-md w-full max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
              <h3 className="text-white font-bold text-sm">📄 領収書発行</h3>
              <button onClick={() => setShowReceiptModal(false)} className="text-gray-400 hover:text-white text-xl leading-none">×</button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-center bg-night-800 rounded-lg py-3">
                <div className="text-gray-500 text-xs">発行金額</div>
                <div className="text-white text-2xl font-bold">¥{(grandTotal || 0).toLocaleString()}</div>
              </div>
              <div>
                <label className="text-gray-400 text-xs">宛名（空欄可）</label>
                <input type="text" value={receiptRecipient} onChange={e => setReceiptRecipient(e.target.value)}
                  placeholder="例: 株式会社○○ / 上様"
                  className="input-field w-full text-sm mt-1" />
              </div>
              <div>
                <label className="text-gray-400 text-xs">用紙サイズ</label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  <button onClick={() => setReceiptPaperSize('80mm')}
                    className={`text-xs py-2 rounded-lg ${receiptPaperSize === '80mm' ? 'bg-emerald-700 text-white' : 'bg-night-800 text-gray-400'}`}>
                    レシート(80mm)
                  </button>
                  <button onClick={() => setReceiptPaperSize('a4')}
                    className={`text-xs py-2 rounded-lg ${receiptPaperSize === 'a4' ? 'bg-emerald-700 text-white' : 'bg-night-800 text-gray-400'}`}>
                    A4
                  </button>
                </div>
              </div>
              <div className="text-[10px] text-gray-500">但し書き: ご飲食代として（固定）</div>
              <button
                disabled={receiptIssuing}
                onClick={async () => {
                  setReceiptIssuing(true)
                  try {
                    const r = await apiClient.post(`/api/receipts/issue/${ticketId}`, {
                      recipient_name: receiptRecipient,
                      note: 'ご飲食代として',
                      paper_size: receiptPaperSize,
                    }, { responseType: 'blob' })
                    const url = URL.createObjectURL(r.data)
                    window.open(url, '_blank')
                    // 履歴更新
                    const h = await apiClient.get(`/api/receipts/history/${ticketId}`)
                    setReceiptHistory(h.data)
                  } catch (e: any) {
                    alert('領収書発行に失敗しました')
                  } finally {
                    setReceiptIssuing(false)
                  }
                }}
                className="btn-primary w-full text-sm py-2.5 disabled:opacity-50"
              >
                {receiptIssuing ? '発行中...' : '領収書を発行 (PDF)'}
              </button>

              {/* 発行履歴 */}
              <div className="border-t border-gray-800 pt-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-xs font-bold">発行履歴</span>
                  <button
                    onClick={async () => {
                      const h = await apiClient.get(`/api/receipts/history/${ticketId}`)
                      setReceiptHistory(h.data)
                    }}
                    className="text-[10px] text-gray-500 hover:text-white"
                  >更新</button>
                </div>
                {receiptHistory.length === 0 && <div className="text-gray-600 text-xs">履歴なし</div>}
                <div className="space-y-1">
                  {receiptHistory.map(r => (
                    <div key={r.id} className="bg-night-800 rounded px-2 py-1.5 flex items-center gap-2 text-xs">
                      <div className="flex-1">
                        <div className="text-white">{r.receipt_no}</div>
                        <div className="text-[10px] text-gray-500">
                          {r.recipient_name || '無記名'} / ¥{r.amount.toLocaleString()} / {r.paper_size}
                        </div>
                      </div>
                      <button
                        onClick={async () => {
                          try {
                            const rr = await apiClient.get(`/api/receipts/reissue/${r.id}`, { responseType: 'blob' })
                            window.open(URL.createObjectURL(rr.data), '_blank')
                          } catch { alert('再発行に失敗しました') }
                        }}
                        className="text-emerald-400 text-[10px] hover:underline"
                      >再発行</button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 会計確認ダイアログ */}
      {pendingAction && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[200]">
          <div className="bg-night-800 border border-night-600 rounded-2xl p-6 w-72 space-y-4 shadow-xl">
            <p className="text-white text-center text-lg font-bold">会計済みですか？</p>
            <div className="flex gap-3">
              <button onClick={() => setPendingAction(null)} className="btn-secondary flex-1">いいえ</button>
              <button onClick={() => { pendingAction(); setPendingAction(null) }} className="btn-primary flex-1">はい</button>
            </div>
          </div>
        </div>
      )}

      {/* 顧客検索モーダル */}
      {showCustomerSearch && (
        <CustomerSearchModal
          storeId={storeId}
          currentId={ticket.customer_id}
          onSelect={id => setCustomerMutation.mutate(id)}
          onClose={() => setShowCustomerSearch(false)}
        />
      )}

      {/* 担当（推しキャスト）選択モーダル */}
      {showCastSearch && (
        <CastAssignModal
          storeId={storeId}
          currentCastName={ticket.featured_cast_name || null}
          onSelect={id => setCastMutation.mutate(id)}
          onClose={() => setShowCastSearch(false)}
        />
      )}
      {/* 対応中キャスト選択モーダル */}
      {showActiveCastsModal && (
        <ActiveCastsModal
          storeId={storeId}
          ticketId={ticketId}
          currentCastIds={(ticket.current_casts || []).map((c: any) => c.cast_id).filter((x: any) => typeof x === 'number')}
          onSubmit={ids => setActiveCastsMutation.mutate(ids)}
          onClose={() => setShowActiveCastsModal(false)}
        />
      )}

      {/* シャンパンメニュー */}
      {showChampagneMenu && (
        <ChampagneMenuModal
          onSelect={(name, price) => {
            setShowChampagneMenu(false)
            setCastSelectItem({ type: 'champagne', label: name, price })
          }}
          onClose={() => setShowChampagneMenu(false)}
        />
      )}

      {/* キャスト選択モーダル */}
      {castSelectItem && (
        <CastSelectModal
          itemType={castSelectItem.type}
          itemLabel={castSelectItem.label}
          storeId={storeId}
          onSubmit={(selections) => {
            const isChampagne = castSelectItem.type === 'champagne'
            if (isChampagne && selections.length > 0) {
              const castsStr = selections.map(s => `${s.castName} ${s.ratio}%`).join('・')
              const itemName = `${castSelectItem.label}［${castsStr}］`
              // 構造化された分配情報（cast_id ベース・全行に同じJSONをコピー）
              const castDistribution = selections.map(s => ({ cast_id: s.castId, ratio: s.ratio }))
              // 最初のキャストに全額、残りは0円マーカー（D時間追跡用）
              const orders = selections.map((s, i) => ({
                item_type: 'champagne',
                item_name: itemName,
                unit_price: i === 0 ? castSelectItem.price : 0,
                quantity: 1,
                cast_id: s.castId,
                cast_distribution: castDistribution,
              }))
              Promise.all(orders.map(o => apiClient.post(`/api/tickets/${ticketId}/orders`, o).then(r => r.data)))
                .then(() => {
                  qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
                  qc.invalidateQueries({ queryKey: ['tickets', storeId] })
                })
            } else if (!isChampagne && selections.length > 0) {
              const { castId, castName } = selections[0]
              const itemName = `${castSelectItem.label}［${castName}］`
              addOrderMutation.mutate({ item_type: castSelectItem.type, item_name: itemName, unit_price: castSelectItem.price, quantity: 1, cast_id: castId })
            }
            setCastSelectItem(null)
          }}
          onClose={() => setCastSelectItem(null)}
        />
      )}

      {/* 合流モーダル */}
      {showJoinModal && (
        <JoinModal
          storeId={storeId}
          onSubmit={data => joinMutation.mutate(data)}
          onClose={() => setShowJoinModal(false)}
          isPending={joinMutation.isPending}
        />
      )}

      {/* 卓情報編集モーダル */}
      {showHeaderEdit && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[60]">
          <div className="bg-night-800 border border-night-600 rounded-2xl p-5 w-80 space-y-4">
            <h3 className="text-white font-bold text-base">卓情報を編集</h3>
            {/* 卓番 */}
            <div className="space-y-1">
              <label className="text-xs text-gray-400">卓番号</label>
              <select
                value={headerEditForm.table_no}
                onChange={e => setHeaderEditForm(f => ({ ...f, table_no: e.target.value }))}
                className="input-field w-full text-sm py-1.5"
              >
                {TABLE_NOS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            {/* 人数 */}
            <div className="space-y-1">
              <label className="text-xs text-gray-400">人数</label>
              <input
                type="number"
                min={1}
                value={headerEditForm.guest_count}
                onChange={e => setHeaderEditForm(f => ({ ...f, guest_count: Math.max(1, parseInt(e.target.value) || 1) }))}
                className="input-field w-full text-sm py-1.5"
              />
            </div>
            {/* N / R */}
            <div className="space-y-1">
              <label className="text-xs text-gray-400">来店種別</label>
              <div className="flex gap-2">
                {['N', 'R'].map(v => (
                  <button
                    key={v}
                    onClick={() => setHeaderEditForm(f => ({ ...f, visit_type: f.visit_type === v ? '' : v }))}
                    className={`flex-1 py-1.5 rounded-lg text-sm font-bold transition-colors ${
                      headerEditForm.visit_type === v
                        ? v === 'N' ? 'bg-blue-700 text-white' : 'bg-purple-700 text-white'
                        : 'bg-night-700 text-gray-400 hover:bg-night-600'
                    }`}
                  >{v}</button>
                ))}
              </div>
            </div>
            {/* スタンダード / プレミアム */}
            <div className="space-y-1">
              <label className="text-xs text-gray-400">プラン</label>
              <div className="flex gap-2">
                {[{ v: 'standard', label: 'スタンダード' }, { v: 'premium', label: 'プレミアム' }].map(({ v, label }) => (
                  <button
                    key={v}
                    onClick={() => setHeaderEditForm(f => ({ ...f, plan_type: v }))}
                    className={`flex-1 py-1.5 rounded-lg text-sm font-bold transition-colors ${
                      headerEditForm.plan_type === v
                        ? v === 'premium' ? 'bg-yellow-700 text-white' : 'bg-gray-600 text-white'
                        : 'bg-night-700 text-gray-400 hover:bg-night-600'
                    }`}
                  >{label}</button>
                ))}
              </div>
            </div>
            {/* 来店動機 */}
            <div className="space-y-1">
              <label className="text-xs text-gray-400">来店動機</label>
              <div className="flex flex-wrap gap-1.5">
                {['', ...MOTIVATION_OPTIONS].map(m => (
                  <button
                    key={m || 'none'}
                    onClick={() => setHeaderEditForm(f => ({ ...f, visit_motivation: m, motivation_cast_id: null }))}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                      headerEditForm.visit_motivation === m
                        ? 'bg-teal-700 text-white'
                        : 'bg-night-700 text-gray-400 hover:bg-night-600'
                    }`}
                  >{m || '未設定'}</button>
                ))}
              </div>
              {MOTIVATION_CAST_REQUIRED.has(headerEditForm.visit_motivation) && (
                <select
                  value={headerEditForm.motivation_cast_id ?? ''}
                  onChange={e => setHeaderEditForm(f => ({ ...f, motivation_cast_id: e.target.value ? Number(e.target.value) : null }))}
                  className="input-field w-full text-sm py-1 mt-1"
                >
                  <option value="">キャスト選択</option>
                  {(castsAll as any[]).filter((c: any) => c.is_active).map((c: any) => (
                    <option key={c.id} value={c.id}>{c.stage_name}</option>
                  ))}
                </select>
              )}
            </div>
            {/* オペレーター名 */}
            <div className="space-y-1">
              <label className="text-xs text-gray-400">操作者名</label>
              <input
                type="text"
                placeholder="名前を入力"
                value={headerEditOperator}
                onChange={e => setHeaderEditOperator(e.target.value)}
                className="input-field w-full text-sm py-1.5"
              />
            </div>
            {headerEditError && <p className="text-red-400 text-xs">{headerEditError}</p>}
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => { setShowHeaderEdit(false); setHeaderEditOperator(''); setHeaderEditError('') }}
                className="flex-1 py-2 rounded-lg bg-night-700 text-gray-300 hover:bg-night-600 text-sm transition-colors"
              >キャンセル</button>
              <button
                onClick={() => {
                  patchHeaderMutation.mutate({
                    table_no: headerEditForm.table_no || undefined,
                    guest_count: headerEditForm.guest_count,
                    visit_type: headerEditForm.visit_type || null,
                    plan_type: headerEditForm.plan_type,
                    visit_motivation: headerEditForm.visit_motivation || null,
                    motivation_cast_id: headerEditForm.motivation_cast_id || null,
                    update_header: true,
                    operator_name: headerEditOperator || null,
                  })
                }}
                disabled={patchHeaderMutation.isPending}
                className="flex-1 py-2 rounded-lg bg-primary-600 hover:bg-primary-500 text-white text-sm font-bold transition-colors disabled:opacity-50"
              >{patchHeaderMutation.isPending ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 削除確認モーダル */}
      {showDeleteModal && (
        <TicketDeleteModal
          ticket={ticket}
          onSubmit={(operator, reason) => {
            apiClient.post(`/api/tickets/${ticketId}/delete`, {
              operator_name: operator,
              reason: reason || null,
            }).then(() => {
              qc.invalidateQueries({ queryKey: ['tickets', storeId] })
              qc.invalidateQueries({ queryKey: ['order-logs', storeId] })
              setShowDeleteModal(false)
              onClose()
            }).catch(e => alert('削除に失敗しました: ' + (e?.response?.data?.detail || e?.message)))
          }}
          onClose={() => setShowDeleteModal(false)}
        />
      )}

      {/* 先退店モーダル */}
      {showSentaitenModal && (
        <SentaitenModal
          currentGuestCount={ticket.guest_count || 1}
          onSubmit={leaveCount => {
            const newCount = (ticket.guest_count || 1) - leaveCount
            apiClient.patch(`/api/tickets/${ticketId}`, { guest_count: newCount }).then(() => {
              qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
              qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
            })
            addOrderMutation.mutate({
              item_type: 'other',
              item_name: `先退店（${leaveCount}名）`,
              unit_price: 0,
              quantity: 1,
            })
            setShowSentaitenModal(false)
          }}
          onClose={() => setShowSentaitenModal(false)}
        />
      )}

      {/* 値引きモーダル */}
      {showDiscountModal && (
        <DiscountModal
          storeId={storeId}
          onSubmit={(amount, reason, operator) => {
            setShowDiscountModal(false)
            addOrderMutation.mutate({
              item_type: 'other',
              item_name: `値引き（${reason}）担当:${operator}`,
              unit_price: -amount,
              quantity: 1,
            })
          }}
          onClose={() => setShowDiscountModal(false)}
        />
      )}

      {/* 先会計モーダル */}
      {showSenkaikeiModal && (
        <SenkaikeiModal
          onSubmit={(amount, paymentMethod) => {
            const methodLabel = { cash: '現金', card: 'カード', code: 'コード決済' }[paymentMethod] ?? paymentMethod
            setShowSenkaikeiModal(false)
            confirmCheckout(() => addOrderMutation.mutate({
              item_type: 'other',
              item_name: `先会計（${methodLabel}）`,
              unit_price: -amount,
              quantity: 1,
            }))
          }}
          onClose={() => setShowSenkaikeiModal(false)}
          isPending={addOrderMutation.isPending}
        />
      )}

      {/* 割り勘モーダル */}
      {showWarikanModal && (
        <WarikanModal
          totalAmount={grandTotal}
          onSubmit={payments => {
            setShowWarikanModal(false)
            confirmCheckout(() => {
              apiClient.post(`/api/tickets/${ticketId}/warikan`, {
                payments: payments.map(({ amount, method }) => ({ amount, method })),
              }).then((res) => {
                // バックエンドで合計0になり自動クローズ済みの場合はcloseを呼ばない
                if (res.data?.is_closed) {
                  qc.invalidateQueries({ queryKey: ['tickets', storeId] })
                  qc.invalidateQueries({ queryKey: ['ticket', ticketId] })
                  onClose()
                } else {
                  const cashTotal = payments.filter(p => p.method === 'cash').reduce((s, p) => s + p.amount, 0)
                  const cardTotal = payments.filter(p => p.method === 'card').reduce((s, p) => s + p.amount, 0)
                  const uniqueMethods = [...new Set(payments.map(p => p.method))]
                  const paymentMethod = uniqueMethods.length === 1 ? uniqueMethods[0] : 'mixed'
                  closeMutation.mutate({ payment_method: paymentMethod, cash_amount: cashTotal, card_amount: cardTotal })
                }
              }).catch(err => console.error('Warikan failed:', err))
            })
          }}
          onClose={() => setShowWarikanModal(false)}
        />
      )}

      {/* 合算モーダル */}
      {showMergeModal && (
        <MergeModal
          storeId={storeId}
          currentTicketId={ticketId}
          onSubmit={targetId => mergeMutation.mutate(targetId)}
          onClose={() => setShowMergeModal(false)}
          isPending={mergeMutation.isPending}
        />
      )}

      {/* 注文アクションパネル（selected行の直下にfixedオーバーレイ） */}
      {(selectedOrderId || editingOrderId) && actionPos && (() => {
        const item = ticket?.order_items?.find((i: any) => i.id === (editingOrderId || selectedOrderId))
        if (!item) return null
        const closePanel = () => { setEditingOrderId(null); setSelectedOrderId(null); setActionPos(null); setOperatorName(''); setOperatorReason(''); setActionMode('add'); setChampEditCasts([]) }
        return (
          <div
            style={{
              position: 'fixed',
              top: actionPos.top,
              left: actionPos.left,
              width: actionPos.width,
              zIndex: 200,
              maxHeight: `calc(100vh - ${actionPos.top + 20}px)`,
              overflowY: 'auto',
            }}
            className="bg-night-800 border border-night-600 border-t-0 rounded-b-xl shadow-2xl px-4 py-3 space-y-2"
            onClick={e => e.stopPropagation()}
          >
            {/* タブ（編集確定入力中は非表示） */}
            {!editingOrderId && (
              <div className="flex gap-1.5">
                <button onClick={() => {
                  addOrderMutation.mutate({
                    item_type: item.item_type,
                    item_name: item.item_name || undefined,
                    unit_price: item.unit_price,
                    quantity: 1,
                    cast_id: item.cast_id,
                  }, { onSuccess: closePanel })
                }}
                  disabled={addOrderMutation.isPending}
                  className="flex-1 text-xs py-1.5 rounded-lg transition-colors font-medium bg-primary-700 text-white hover:bg-primary-600 disabled:opacity-50">
                  追加
                </button>
                <button onClick={() => setActionMode('delete')}
                  className={`flex-1 text-xs py-1.5 rounded-lg transition-colors font-medium ${actionMode === 'delete' ? 'bg-red-800/80 text-red-200' : 'bg-night-700 text-gray-400 hover:bg-night-600'}`}>
                  削除
                </button>
                <button onClick={() => {
                  setActionMode('edit')
                  const groupItems = (ticket?.order_items || []).filter((i: any) =>
                    !i.canceled_at &&
                    i.item_type === item.item_type &&
                    (i.item_name ?? '') === (item.item_name ?? '') &&
                    i.unit_price === item.unit_price
                  )
                  const groupQty = groupItems.reduce((s: number, i: any) => s + i.quantity, 0)
                  setEditingGroupMaxQty(groupQty)
                  setEditingGroupItemIds(groupItems.map((i: any) => i.id))
                  setEditingQty(groupQty)
                  setEditingOrderId(selectedOrderId)
                  setOperatorName('')
                  setOperatorReason('')
                  // シャンパンの場合: cast_distribution 優先・無ければ item_name パース
                  if (item.item_type === 'champagne') {
                    // 同一グループ（同じ item_name）の全行を取得
                    const champItems = (ticket.order_items || []).filter((i: any) =>
                      i.item_type === 'champagne' && i.item_name === item.item_name && !i.canceled_at
                    )
                    // cast_distribution を持つ代表行を探す
                    const distHolder = champItems.find((i: any) => Array.isArray(i.cast_distribution) && i.cast_distribution.length > 0)
                    // 名前 → id 引き当て用（castsAll 全店舗キャスト）
                    const findCastByName = (name: string): number | null => {
                      const c = (castsAll as any[]).find((x: any) => x.stage_name === name)
                      return c ? c.id : null
                    }
                    if (distHolder && distHolder.cast_distribution) {
                      // 構造化データから組み立て（cast_id でキャスト名解決）
                      const parsed = distHolder.cast_distribution.map((d: any) => {
                        const c = (castsAll as any[]).find((x: any) => x.id === d.cast_id)
                        return {
                          castId: d.cast_id,
                          castName: c?.stage_name || `Cast${d.cast_id}`,
                          ratio: d.ratio || 0,
                        }
                      })
                      setChampEditCasts(parsed)
                    } else {
                      // 旧形式: item_name パース → castsAll から名前で引き当て
                      const inner = (item.item_name || '').match(/[［\[](.+?)[］\]]/)?.[1] || ''
                      const parsed = inner.split('・').map((p: string) => {
                        const m = p.match(/^(.+?)\s+(\d+)%$/)
                        const castName = m ? m[1] : p
                        const ratio = m ? parseInt(m[2]) : 0
                        return { castId: findCastByName(castName), castName, ratio }
                      }).filter((c: { castName: string; ratio: number }) => c.castName)
                      setChampEditCasts(parsed)
                    }
                  } else {
                    setChampEditCasts([])
                  }
                }}
                  className={`flex-1 text-xs py-1.5 rounded-lg transition-colors font-medium ${actionMode === 'edit' ? 'bg-gray-600 text-white' : 'bg-night-700 text-gray-400 hover:bg-night-600'}`}>
                  編集
                </button>
                <button onClick={closePanel}
                  className="flex-1 text-xs py-1.5 rounded-lg bg-night-700 text-gray-500 hover:bg-night-600 transition-colors">
                  ✕
                </button>
              </div>
            )}

            {/* 削除・編集モード（operator入力） */}
            {((!editingOrderId && actionMode === 'delete') || editingOrderId) && (
              <>
                {editingOrderId && item.item_type !== 'champagne' && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400 shrink-0">数量</span>
                    <input type="number" min={1} max={editingGroupMaxQty} value={editingQty}
                      onChange={e => setEditingQty(Math.min(editingGroupMaxQty, Math.max(1, Number(e.target.value))))}
                      className="input-field w-20 text-center text-sm py-1" />
                    <span className="text-xs text-gray-500">/ {editingGroupMaxQty}</span>
                  </div>
                )}
                {/* シャンパン: キャスト配分率編集（追加・削除可） */}
                {editingOrderId && item.item_type === 'champagne' && (() => {
                  const totalRatio = champEditCasts.reduce((s, c) => s + c.ratio, 0)
                  const availableCasts = (castsAll as any[]).filter(
                    (c: any) => !champEditCasts.some(x => x.castId === c.id)
                  )
                  return (
                    <div className="space-y-1.5 p-2 bg-night-700 rounded-lg">
                      <p className="text-xs text-gray-400 font-medium">インセンティブ配分</p>
                      {champEditCasts.map((c, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <span className="text-xs text-gray-300 flex-1 truncate">{c.castName}</span>
                          <input
                            type="number" min={0} max={100} value={c.ratio}
                            onFocus={e => e.target.select()}
                            onChange={e => setChampEditCasts(prev => prev.map((x, i) =>
                              i === idx ? { ...x, ratio: Math.min(100, Math.max(0, Number(e.target.value) || 0)) } : x
                            ))}
                            className="input-field w-16 text-center text-xs py-0.5"
                          />
                          <span className="text-gray-400 text-xs">%</span>
                          <button
                            onClick={() => setChampEditCasts(prev => prev.filter((_, i) => i !== idx))}
                            className="text-red-400 hover:text-red-300 text-xs px-1.5"
                            title="削除">×</button>
                        </div>
                      ))}
                      {availableCasts.length > 0 && (
                        <select
                          value=""
                          onChange={e => {
                            const cid = Number(e.target.value)
                            if (!cid) return
                            const c = (castsAll as any[]).find((x: any) => x.id === cid)
                            if (c) {
                              setChampEditCasts(prev => [...prev, { castId: cid, castName: c.stage_name, ratio: 0 }])
                            }
                          }}
                          className="input-field w-full text-xs py-0.5"
                        >
                          <option value="">＋ キャスト追加</option>
                          {availableCasts.map((c: any) => (
                            <option key={c.id} value={c.id}>{c.stage_name}</option>
                          ))}
                        </select>
                      )}
                      <p className={`text-xs text-right font-medium ${totalRatio === 100 ? 'text-green-400' : 'text-red-400'}`}>
                        合計 {totalRatio}%{totalRatio !== 100 && ' ← 100%にしてください'}
                      </p>
                    </div>
                  )
                })()}
                <input type="text" placeholder="担当者名（必須）" value={operatorName}
                  onChange={e => setOperatorName(e.target.value)}
                  className="input-field w-full text-xs py-1" autoFocus />
                <input type="text" placeholder="理由（任意）" value={operatorReason}
                  onChange={e => setOperatorReason(e.target.value)}
                  className="input-field w-full text-xs py-1" />
                <div className="flex gap-2 justify-end">
                  {!editingOrderId ? (
                    <button
                      onClick={() => cancelOrderMutation.mutate({ itemId: selectedOrderId!, operator: operatorName, reason: operatorReason })}
                      disabled={!operatorName.trim() || cancelOrderMutation.isPending}
                      className="text-xs px-3 py-1.5 bg-red-800/60 hover:bg-red-700/70 text-red-300 rounded-lg transition-colors disabled:opacity-40">
                      削除する
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        if (item.item_type === 'champagne' && champEditCasts.length > 0) {
                          // シャンパン: 全員 castId 必須
                          const missing = champEditCasts.filter(c => typeof c.castId !== 'number')
                          if (missing.length > 0) {
                            alert(`キャストがリンクされていません: ${missing.map(m => m.castName).join(', ')}\n一旦×ボタンで削除して、プルダウンから追加し直してください。`)
                            return
                          }
                          const baseName = (item.item_name || '').replace(/[［\[].*[］\]]/, '').trim()
                          const useBracket = (item.item_name || '').includes('［') ? '［' : '['
                          const closeBracket = useBracket === '［' ? '］' : ']'
                          const castsStr = champEditCasts.map(c => `${c.castName} ${c.ratio}%`).join('・')
                          const newItemName = `${baseName}${useBracket}${castsStr}${closeBracket}`
                          const distribution = champEditCasts.map(c => ({ cast_id: c.castId as number, ratio: c.ratio }))
                          updateChampagneMutation.mutate({ oldName: item.item_name, newName: newItemName, operator: operatorName, reason: operatorReason, distribution })
                        } else if (editingGroupItemIds.length > 1) {
                          groupReduceMutation.mutate({ item, targetQty: editingQty, operator: operatorName, reason: operatorReason })
                        } else {
                          updateOrderMutation.mutate({ itemId: editingOrderId!, quantity: editingQty, operator: operatorName, reason: operatorReason })
                        }
                      }}
                      disabled={
                        !operatorName.trim() ||
                        updateOrderMutation.isPending ||
                        groupReduceMutation.isPending ||
                        updateChampagneMutation.isPending ||
                        (item.item_type === 'champagne' && champEditCasts.reduce((s, c) => s + c.ratio, 0) !== 100)
                      }
                      className="text-xs px-3 py-1.5 bg-primary-700 hover:bg-primary-600 text-white rounded-lg transition-colors disabled:opacity-50">
                      確定
                    </button>
                  )}
                  <button onClick={closePanel}
                    className="text-xs px-3 py-1.5 bg-night-600 hover:bg-night-500 text-gray-400 rounded-lg transition-colors">
                    キャンセル
                  </button>
                </div>
              </>
            )}
          </div>
        )
      })()}

      {showLog && ticket && (
        <TicketLogModal ticket={ticket} onClose={() => setShowLog(false)} />
      )}
    </div>
  )
}

function JoinModal({ storeId, onSubmit, onClose, isPending }: {
  storeId: number
  onSubmit: (data: {
    guest_count: number
    visit_type: string
    customer_name?: string
    visit_motivation?: string
    motivation_cast_id?: number | null
    motivation_note?: string
    plan_type: string
  }) => void
  onClose: () => void
  isPending: boolean
}) {
  const [guestCount, setGuestCount] = useState(1)
  const [visitType, setVisitType] = useState('N')
  const [customerName, setCustomerName] = useState('')
  const [motivation, setMotivation] = useState('')
  const [motivationCastId, setMotivationCastId] = useState<number | null>(null)
  const [motivationNote, setMotivationNote] = useState('')
  const [planType, setPlanType] = useState('standard')

  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
  })
  const casts = (castsAll as any[]).filter((c: any) => c.is_active)

  const needsCast = MOTIVATION_CAST_REQUIRED.has(motivation)
  const needsNote = motivation === '紹介'

  const row = "flex items-center gap-2"
  const label = "text-xs text-gray-400 w-20 shrink-0"

  const handleSubmit = () => {
    onSubmit({
      guest_count: guestCount,
      visit_type: visitType,
      customer_name: customerName || undefined,
      visit_motivation: motivation || undefined,
      motivation_cast_id: needsCast ? motivationCastId : null,
      motivation_note: needsNote ? motivationNote : undefined,
      plan_type: planType,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[80] p-4">
      <div className="card w-full max-w-sm space-y-2.5">
        <div className="flex justify-between items-center mb-1">
          <h3 className="font-bold text-white">合流</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        <div className={row}>
          <span className={label}>人数</span>
          <select value={guestCount} onChange={e => setGuestCount(Number(e.target.value))} className="input-field flex-1 text-sm py-1.5">
            {Array.from({length: 20}, (_, i) => i + 1).map(n => <option key={n} value={n}>{n}名</option>)}
          </select>
        </div>

        <div className={row}>
          <span className={label}>区分</span>
          <div className="flex gap-1.5 flex-1">
            {['N', 'R'].map(v => (
              <button key={v} onClick={() => setVisitType(v)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${visitType === v ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                {v}
              </button>
            ))}
          </div>
        </div>

        <div className={row}>
          <span className={label}>顧客名</span>
          <input type="text" value={customerName} onChange={e => setCustomerName(e.target.value)}
            placeholder="顧客名（任意）"
            className="input-field flex-1 text-sm py-1.5" />
        </div>

        <div className={row}>
          <span className={label}>来店動機</span>
          <select value={motivation} onChange={e => { setMotivation(e.target.value); setMotivationCastId(null); setMotivationNote('') }}
            className="input-field flex-1 text-sm py-1.5">
            <option value="">未選択</option>
            {MOTIVATION_OPTIONS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {needsCast && (
          <div className={row}>
            <span className={label}>キャスト</span>
            <select value={motivationCastId ?? ''} onChange={e => setMotivationCastId(e.target.value ? Number(e.target.value) : null)}
              className="input-field flex-1 text-sm py-1.5">
              <option value="">選択してください</option>
              {casts.map((c: any) => <option key={c.id} value={c.id}>{c.stage_name}</option>)}
            </select>
          </div>
        )}

        {needsNote && (
          <div className={row}>
            <span className={label}>紹介者</span>
            <input type="text" value={motivationNote} onChange={e => setMotivationNote(e.target.value)}
              placeholder="紹介者名を入力"
              className="input-field flex-1 text-sm py-1.5" />
          </div>
        )}

        <div className={row}>
          <span className={label}>プラン</span>
          <div className="flex gap-1.5 flex-1">
            {['standard', 'premium'].map(p => (
              <button key={p} onClick={() => setPlanType(p)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${planType === p ? 'bg-primary-600 text-white' : 'btn-secondary'}`}>
                {p === 'premium' ? 'プレミアム' : 'スタンダード'}
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={handleSubmit} disabled={isPending}
            className="btn-primary flex-1 disabled:opacity-50">合流追加</button>
        </div>
      </div>
    </div>
  )
}

function MergeModal({ storeId, currentTicketId, onSubmit, onClose, isPending }: {
  storeId: number
  currentTicketId: number
  onSubmit: (targetId: number) => void
  onClose: () => void
  isPending: boolean
}) {
  const { data: tickets = [] } = useQuery({
    queryKey: ['tickets', storeId, 'open'],
    queryFn: () => apiClient.get('/api/tickets', { params: { store_id: storeId, is_closed: false } }).then(r => r.data),
  })

  const others = (tickets as any[]).filter((t: any) => t.id !== currentTicketId)

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[80] p-4">
      <div className="card w-full max-w-sm space-y-3">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">合算 — 伝票を選択</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <p className="text-xs text-gray-400">選択した伝票の注文をすべてこの伝票に移動し、元の伝票を閉じます。</p>
        <div className="space-y-1.5 max-h-72 overflow-y-auto">
          {others.map((t: any) => (
            <button key={t.id} onClick={() => onSubmit(t.id)} disabled={isPending}
              className="w-full text-left px-3 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors disabled:opacity-50">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white">{t.table_no || '—'}</span>
                  {t.visit_type && <span className={`badge text-xs ${t.visit_type === 'N' ? 'bg-blue-900/40 text-blue-400' : 'bg-purple-900/40 text-purple-400'}`}>{t.visit_type}</span>}
                  <span className="text-gray-400 text-xs">{t.guest_count}名</span>
                  {t.customer_name && <span className="text-gray-400 text-xs truncate">{t.customer_name}</span>}
                </div>
                <span className="text-pink-400 font-medium shrink-0">¥{calcTicketGrandTotal(t).toLocaleString()}</span>
              </div>
            </button>
          ))}
          {others.length === 0 && (
            <p className="text-center text-gray-500 text-sm py-6">合算できる伝票がありません</p>
          )}
        </div>
        <button onClick={onClose} className="btn-secondary w-full">キャンセル</button>
      </div>
    </div>
  )
}

function DiscountModal({ storeId, onSubmit, onClose }: {
  storeId: number
  onSubmit: (amount: number, reason: string, operator: string) => void
  onClose: () => void
}) {
  const [input, setInput] = useState('')
  const [reasonType, setReasonType] = useState<'端数カット' | 'その他'>('端数カット')
  const [customReason, setCustomReason] = useState('')
  const [operator, setOperator] = useState('')

  const { data: staffList = [] } = useQuery({
    queryKey: ['staff-for-discount', storeId],
    queryFn: () => apiClient.get('/api/staff', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
  })

  const amount = parseInt(input, 10) || 0
  const reason = reasonType === 'その他' ? (customReason.trim() || 'その他') : '端数カット'
  const canSubmit = amount > 0 && operator.trim()

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">値引き</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        <div>
          <label className="text-xs text-gray-400 block mb-1">値引き金額</label>
          <div className="flex items-center gap-2">
            <span className="text-gray-400">¥</span>
            <input type="number" min={1} value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="0"
              className="input-field flex-1 text-lg text-right"
              autoFocus />
          </div>
        </div>

        <div>
          <label className="text-xs text-gray-400 block mb-1">理由</label>
          <select value={reasonType} onChange={e => setReasonType(e.target.value as any)}
            className="input-field w-full">
            <option value="端数カット">端数カット</option>
            <option value="その他">その他</option>
          </select>
          {reasonType === 'その他' && (
            <input type="text" placeholder="理由を入力" value={customReason}
              onChange={e => setCustomReason(e.target.value)}
              className="input-field w-full mt-2 text-sm" />
          )}
        </div>

        <div>
          <label className="text-xs text-gray-400 block mb-1">担当者（必須）</label>
          <select value={operator} onChange={e => setOperator(e.target.value)}
            className="input-field w-full">
            <option value="">選択してください</option>
            {(staffList as any[]).map((m: any) => (
              <option key={m.id} value={m.name}>{m.name}（{m.employee_type === 'staff' ? '社員' : 'アルバイト'}）</option>
            ))}
          </select>
        </div>

        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => { if (canSubmit) onSubmit(amount, reason, operator) }}
            disabled={!canSubmit}
            className="btn-primary flex-1 disabled:opacity-40">
            実行
          </button>
        </div>
      </div>
    </div>
  )
}

function SenkaikeiModal({ onSubmit, onClose, isPending }: {
  onSubmit: (amount: number, paymentMethod: string) => void
  onClose: () => void
  isPending: boolean
}) {
  const [input, setInput] = useState('')
  const [paymentMethod, setPaymentMethod] = useState<string | null>(null)
  const amount = parseInt(input, 10) || 0
  const canSubmit = amount > 0 && paymentMethod !== null && !isPending

  const PAYMENT_METHODS = [
    { key: 'cash', label: '現金' },
    { key: 'card', label: 'カード' },
    { key: 'code', label: 'コード決済' },
  ]

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[80] p-4">
      <div className="card w-full max-w-xs space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">先会計</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        {/* 支払方法 */}
        <div>
          <p className="text-xs text-gray-400 mb-2">支払方法</p>
          <div className="flex gap-2">
            {PAYMENT_METHODS.map(m => (
              <button key={m.key} onClick={() => setPaymentMethod(m.key)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${paymentMethod === m.key ? 'bg-primary-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* 金額入力 */}
        <div>
          <p className="text-xs text-gray-400 mb-2">金額</p>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">¥</span>
            <input
              type="number"
              min={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="0"
              className="input-field w-full text-lg pl-8"
              autoFocus
            />
          </div>
        </div>

        {amount > 0 && paymentMethod && (
          <div className="bg-blue-900/20 border border-blue-700/40 rounded-xl px-4 py-2 text-center">
            <span className="text-blue-300 font-bold text-lg">¥{amount.toLocaleString()}</span>
            <span className="text-blue-400 text-xs ml-2">
              {PAYMENT_METHODS.find(m => m.key === paymentMethod)?.label}で先会計
            </span>
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => { if (canSubmit) onSubmit(amount, paymentMethod!) }}
            disabled={!canSubmit}
            className="btn-primary flex-1 disabled:opacity-40">
            会計実行
          </button>
        </div>
      </div>
    </div>
  )
}

const WARIKAN_PAYMENT_OPTIONS = [
  { key: '', label: '支払方法' },
  { key: 'cash', label: '現金' },
  { key: 'card', label: 'カード決済' },
  { key: 'code', label: 'コード決済' },
]

function WarikanModal({ totalAmount, onSubmit, onClose }: {
  totalAmount: number
  onSubmit: (payments: { amount: number; method: string }[]) => void
  onClose: () => void
}) {
  const [count, setCount] = useState(2)
  const [amounts, setAmounts] = useState<string[]>(Array(2).fill(''))
  const [methods, setMethods] = useState<string[]>(Array(2).fill(''))

  const handleCountChange = (n: number) => {
    setCount(n)
    setAmounts(prev => {
      const next = Array(n).fill('')
      for (let i = 0; i < Math.min(prev.length, n); i++) next[i] = prev[i]
      return next
    })
    setMethods(prev => {
      const next = Array(n).fill('')
      for (let i = 0; i < Math.min(prev.length, n); i++) next[i] = prev[i]
      return next
    })
  }

  const entered = amounts.reduce((s, v) => s + (parseInt(v, 10) || 0), 0)
  const remaining = Math.round(totalAmount - entered)

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[80] p-4">
      <div className="card w-full max-w-sm space-y-3">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">割り勘</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        {/* 合計表示 */}
        <div className="bg-night-700 rounded-xl px-4 py-2 flex justify-between items-center">
          <span className="text-xs text-gray-400">合計金額</span>
          <span className="font-bold text-primary-400">¥{totalAmount.toLocaleString()}</span>
        </div>

        {/* 人数選択 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 w-16 shrink-0">人数</span>
          <div className="flex gap-1.5 flex-wrap flex-1">
            {[2,3,4,5,6,7,8,9,10].map(n => (
              <button key={n} onClick={() => handleCountChange(n)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${count === n ? 'bg-primary-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
                {n}名
              </button>
            ))}
          </div>
        </div>

        {/* 各人の金額入力 */}
        <div className="space-y-1.5 max-h-52 overflow-y-auto">
          {amounts.map((v, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-10 shrink-0 text-right">{i + 1}人目</span>
              <div className="relative w-28 shrink-0">
                <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 text-sm">¥</span>
                <input
                  type="number"
                  min={0}
                  value={v}
                  onChange={e => setAmounts(prev => { const next = [...prev]; next[i] = e.target.value; return next })}
                  placeholder="0"
                  className="input-field w-full text-sm pl-6 py-1.5"
                />
              </div>
              <select
                value={methods[i]}
                onChange={e => setMethods(prev => { const next = [...prev]; next[i] = e.target.value; return next })}
                className="input-field flex-1 text-xs py-1.5">
                {WARIKAN_PAYMENT_OPTIONS.map(o => (
                  <option key={o.key} value={o.key} disabled={o.key === ''}>{o.label}</option>
                ))}
              </select>
              {remaining > 0 && (
                <button
                  onClick={() => setAmounts(prev => {
                    const next = [...prev]
                    next[i] = String((parseInt(prev[i], 10) || 0) + remaining)
                    return next
                  })}
                  className="text-xs text-primary-400 hover:text-primary-300 shrink-0 whitespace-nowrap">
                  +残額
                </button>
              )}
              <span className="text-xs text-gray-400 w-16 shrink-0 text-right">
                {v ? `¥${(parseInt(v, 10) || 0).toLocaleString()}` : '—'}
              </span>
            </div>
          ))}
        </div>

        {/* 残金額 */}
        <div className={`rounded-xl px-4 py-2.5 flex justify-between items-center ${remaining < 0 ? 'bg-red-900/30 border border-red-700/40' : remaining === 0 ? 'bg-green-900/30 border border-green-700/40' : 'bg-night-700'}`}>
          <span className="text-xs text-gray-400">残金額</span>
          <span className={`font-bold text-lg ${remaining < 0 ? 'text-red-400' : remaining === 0 ? 'text-green-400' : 'text-white'}`}>
            ¥{remaining.toLocaleString()}
          </span>
        </div>

        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => {
              const payments = amounts
                .map((v, i) => ({ amount: parseInt(v, 10) || 0, method: methods[i] }))
                .filter(p => p.amount > 0)
              onSubmit(payments)
            }}
            disabled={Math.round(remaining) !== 0 || amounts.some((v, i) => (parseInt(v, 10) || 0) > 0 && !methods[i])}
            className="btn-primary flex-1 disabled:opacity-40">
            会計実行
          </button>
        </div>
      </div>
    </div>
  )
}

function SentaitenModal({ currentGuestCount, onSubmit, onClose }: {
  currentGuestCount: number
  onSubmit: (leaveCount: number) => void
  onClose: () => void
}) {
  const [leaveCount, setLeaveCount] = useState(1)
  const maxLeave = currentGuestCount - 1

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[80] p-4">
      <div className="card w-full max-w-xs space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">先退店</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        <div className="bg-night-700 rounded-xl px-4 py-2 flex justify-between items-center">
          <span className="text-xs text-gray-400">現在の人数</span>
          <span className="font-bold text-white">{currentGuestCount}名</span>
        </div>

        {maxLeave <= 0 ? (
          <p className="text-sm text-gray-500 text-center py-2">先退店できる人数がいません（1名のみ）</p>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400 shrink-0">退店人数</span>
              <select
                value={leaveCount}
                onChange={e => setLeaveCount(Number(e.target.value))}
                className="input-field flex-1 text-sm">
                {Array.from({ length: maxLeave }, (_, i) => i + 1).map(n => (
                  <option key={n} value={n}>{n}名</option>
                ))}
              </select>
            </div>

            <div className="bg-orange-900/20 border border-orange-700/40 rounded-xl px-4 py-2 flex justify-between items-center">
              <span className="text-xs text-orange-400">退店後の残り人数</span>
              <span className="font-bold text-orange-300">{currentGuestCount - leaveCount}名</span>
            </div>
          </>
        )}

        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button
            onClick={() => onSubmit(leaveCount)}
            disabled={maxLeave <= 0}
            className="btn-primary flex-1 disabled:opacity-40">
            実行
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────
// キャスト勤怠
// ─────────────────────────────────────────
// 30分刻みの時刻スロット生成（営業時間: 18:00〜30:00）
// label: バー表記 "24:00" 等, value: 実際の HH:MM をバックエンドへ送る
function genTimeSlots(): { label: string; value: string }[] {
  const slots: { label: string; value: string }[] = []
  for (let i = 18 * 2; i <= 30 * 2; i++) {
    const totalMins = i * 30
    const displayH = Math.floor(totalMins / 60)
    const displayM = totalMins % 60
    const actualH = displayH % 24
    const label = `${displayH.toString().padStart(2, '0')}:${displayM.toString().padStart(2, '0')}`
    const value = `${actualH.toString().padStart(2, '0')}:${displayM.toString().padStart(2, '0')}`
    slots.push({ label, value })
  }
  return slots
}
const TIME_SLOTS = genTimeSlots()

// 実際のHH:MM → バー表記（00:00 → 24:00）
function toBarDisplay(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number)
  const displayH = h < 12 ? h + 24 : h
  return `${displayH.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

// バー表記HH:MM → 実HH:MM（"24:30" → "00:30"）
function barToActual(bar: string): string {
  const [h, m] = bar.split(':').map(Number)
  if (isNaN(h) || isNaN(m)) return bar
  return `${(h % 24).toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

// 時刻選択モーダル（プルダウン＋手入力、出勤時は遅刻/当欠タブ付き）
function TimePickerModal({ title, defaultValue, onSelect, onClose, showStatusTabs = false }: {
  title: string
  defaultValue: string
  onSelect: (value: string, opts?: { is_late?: boolean; is_absent?: boolean }) => void
  onClose: () => void
  showStatusTabs?: boolean
}) {
  const nearest = TIME_SLOTS.find(s => s.value === defaultValue)?.value ?? TIME_SLOTS[0].value
  const [selected, setSelected] = useState(nearest)
  const [manual, setManual] = useState(toBarDisplay(nearest))
  const [useManual, setUseManual] = useState(false)
  const [status, setStatus] = useState<'normal' | 'late' | 'absent'>('normal')

  const handleSelect = (value: string) => {
    setSelected(value)
    setManual(toBarDisplay(value))
    setUseManual(false)
  }

  const handleManualChange = (v: string) => {
    setManual(v)
    setUseManual(true)
    if (/^\d{1,2}:\d{2}$/.test(v)) {
      const actual = barToActual(v)
      const match = TIME_SLOTS.find(s => s.value === actual)
      if (match) { setSelected(match.value); setUseManual(false) }
    }
  }

  const handleConfirm = () => {
    if (status === 'absent') {
      onSelect('', { is_absent: true })
      return
    }
    const time = useManual && /^\d{1,2}:\d{2}$/.test(manual) ? barToActual(manual) : selected
    onSelect(time, { is_late: status === 'late' })
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4" onClick={onClose}>
      <div className="card w-full max-w-xs space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white text-sm">{title}</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        {/* 遅刻/当欠タブ（出勤時のみ） */}
        {showStatusTabs && (
          <div className="flex gap-1.5">
            {(['normal', 'late', 'absent'] as const).map(s => (
              <button key={s} onClick={() => setStatus(s)}
                className={`flex-1 text-xs py-1.5 rounded-lg transition-colors font-medium ${
                  status === s
                    ? s === 'normal' ? 'bg-emerald-700 text-white'
                      : s === 'late' ? 'bg-yellow-700 text-white'
                      : 'bg-red-800 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}>
                {s === 'normal' ? '通常' : s === 'late' ? '遅刻' : '当欠'}
              </button>
            ))}
          </div>
        )}

        {/* 当欠は時刻選択不要 */}
        {status !== 'absent' && (
          <>
            <input type="text" value={manual} onChange={e => handleManualChange(e.target.value)}
              placeholder="例: 24:30"
              className={`input-field w-full text-center text-lg font-mono py-2 ${useManual ? 'border-primary-500' : ''}`} />
            <select value={selected} onChange={e => handleSelect(e.target.value)}
              className="input-field w-full text-sm py-1" size={7}>
              {TIME_SLOTS.map(slot => (
                <option key={slot.value} value={slot.value}>{slot.label}</option>
              ))}
            </select>
          </>
        )}

        {status === 'absent' && (
          <div className="text-center text-red-400 text-sm py-4 bg-red-900/20 rounded-lg">
            当欠として登録します
          </div>
        )}

        <div className="flex gap-2">
          <button onClick={handleConfirm}
            className={`flex-1 py-2 text-white rounded-lg text-sm font-medium transition-colors ${
              status === 'absent' ? 'bg-red-700 hover:bg-red-600' :
              status === 'late' ? 'bg-yellow-700 hover:bg-yellow-600' :
              'bg-primary-700 hover:bg-primary-600'
            }`}>
            確定
          </button>
          <button onClick={onClose}
            className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm transition-colors">
            キャンセル
          </button>
        </div>
      </div>
    </div>
  )
}

function HelpClockInForm({ storeId, helpStoreId, setHelpStoreId, helpCastName, setHelpCastName, onSubmit, onCancel, isPending }: {
  storeId: number
  helpStoreId: number | ''
  setHelpStoreId: (v: number | '') => void
  helpCastName: string
  setHelpCastName: (v: string) => void
  onSubmit: (name: string, fromStoreId: number, time: string) => void
  onCancel: () => void
  isPending: boolean
}) {
  const { stores } = useAuthStore()
  const otherStores = stores.filter(s => s.id !== storeId)
  const timeOptions = (() => {
    const opts: string[] = []
    for (let h = 12; h < 36; h++) {
      opts.push(`${String(h).padStart(2, '0')}:00`)
      opts.push(`${String(h).padStart(2, '0')}:30`)
    }
    return opts
  })()
  const [time, setTime] = useState(() => {
    const n = new Date()
    const h = n.getHours() < 12 ? n.getHours() + 24 : n.getHours()
    const m = n.getMinutes() < 30 ? '00' : '30'
    return `${String(h).padStart(2, '0')}:${m}`
  })

  const canSubmit = helpCastName.trim() && helpStoreId !== ''

  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs text-gray-400 block mb-1">ヘルプ元店舗</label>
        <select value={helpStoreId} onChange={e => setHelpStoreId(e.target.value ? Number(e.target.value) : '')}
          className="input-field w-full text-sm">
          <option value="">店舗を選択</option>
          {otherStores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">キャスト名</label>
        <input type="text" value={helpCastName} onChange={e => setHelpCastName(e.target.value)}
          placeholder="キャスト名を入力" className="input-field w-full text-sm" autoFocus />
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">出勤時間</label>
        <select value={time} onChange={e => setTime(e.target.value)} className="input-field w-full text-sm">
          {timeOptions.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={onCancel} className="btn-secondary flex-1 text-sm py-2">キャンセル</button>
        <button
          onClick={() => canSubmit && onSubmit(helpCastName.trim(), helpStoreId as number, time)}
          disabled={!canSubmit || isPending}
          className="flex-1 text-sm py-2 rounded-lg bg-blue-700 hover:bg-blue-600 text-white font-medium disabled:opacity-40 transition-colors"
        >
          出勤
        </button>
      </div>
    </div>
  )
}

function TaikenClockInForm({ taikenName, setTaikenName, onSubmit, onCancel, isPending }: {
  taikenName: string
  setTaikenName: (v: string) => void
  onSubmit: (name: string, time: string, hourlyRate: number) => void
  onCancel: () => void
  isPending: boolean
}) {
  const timeOptions = (() => {
    const opts: string[] = []
    for (let h = 12; h < 36; h++) {
      opts.push(`${String(h).padStart(2, '0')}:00`)
      opts.push(`${String(h).padStart(2, '0')}:30`)
    }
    return opts
  })()
  const [time, setTime] = useState(() => {
    const n = new Date()
    const h = n.getHours() < 12 ? n.getHours() + 24 : n.getHours()
    const m = n.getMinutes() < 30 ? '00' : '30'
    return `${String(h).padStart(2, '0')}:${m}`
  })
  const [hourlyRate, setHourlyRate] = useState('1400')

  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs text-gray-400 block mb-1">キャスト名</label>
        <input type="text" value={taikenName} onChange={e => setTaikenName(e.target.value)}
          placeholder="体験入店キャスト名" className="input-field w-full text-sm" autoFocus />
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">時給（円）</label>
        <input type="number" value={hourlyRate} onChange={e => setHourlyRate(e.target.value)}
          placeholder="1400" className="input-field w-full text-sm" min={0} />
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">出勤時間</label>
        <select value={time} onChange={e => setTime(e.target.value)} className="input-field w-full text-sm">
          {timeOptions.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={onCancel} className="btn-secondary flex-1 text-sm py-2">キャンセル</button>
        <button
          onClick={() => taikenName.trim() && onSubmit(taikenName.trim(), time, parseInt(hourlyRate) || 1400)}
          disabled={!taikenName.trim() || isPending}
          className="flex-1 text-sm py-2 rounded-lg bg-pink-700 hover:bg-pink-600 text-white font-medium disabled:opacity-40 transition-colors"
        >
          体験入店
        </button>
      </div>
    </div>
  )
}

function ActiveCastsView({ storeId, tickets, onTicketClick, onOpenActiveCastsModal }: { storeId: number; tickets: any[]; onTicketClick: (id: number) => void; onOpenActiveCastsModal: (ticket: any) => void }) {
  const qc = useQueryClient()
  // 出勤中キャスト一覧
  const { data: shifts = [] } = useQuery({
    queryKey: ['casts-working', storeId],
    queryFn: () => apiClient.get(`/api/casts/attendance/working/${storeId}`).then(r => r.data),
    enabled: !!storeId,
    refetchInterval: 15000,
  })
  // ティッシュ配り中
  const { data: activeTissue = [] } = useQuery({
    queryKey: ['tissue-active', storeId],
    queryFn: () => apiClient.get('/api/tissue/active', { params: { store_id: storeId } }).then(r => r.data),
    enabled: !!storeId,
    refetchInterval: 15000,
  })
  // 入力中の枚数
  const [tissueCounts, setTissueCounts] = useState<Record<number, string>>({})
  // キャストアクションポップアップ
  const [castActionTarget, setCastActionTarget] = useState<{ cast_id: number; cast_name: string; x: number; y: number } | null>(null)

  const completeTissue = (tdId: number) => {
    const v = parseInt(tissueCounts[tdId] || '0', 10)
    if (isNaN(v) || v < 0) return
    apiClient.post(`/api/tissue/${tdId}/complete`, { count: v }).then(() => {
      qc.invalidateQueries({ queryKey: ['tissue-active', storeId] })
      qc.invalidateQueries({ queryKey: ['casts-working', storeId] })
    })
  }
  const cancelTissue = (tdId: number) => {
    if (!confirm('この配り中を取り消しますか？')) return
    apiClient.delete(`/api/tissue/${tdId}`).then(() => {
      qc.invalidateQueries({ queryKey: ['tissue-active', storeId] })
    })
  }

  // 配り中のキャスト ID 集合（出勤中の表示から除外するため）
  const tissueCastIds = new Set((activeTissue as any[]).map((t: any) => t.cast_id))

  // キャスト別の現在担当卓（current_casts ベース）
  const castToTicket: Record<number, any> = {}
  for (const t of tickets) {
    for (const c of (t.current_casts || [])) {
      if (typeof c.cast_id === 'number') castToTicket[c.cast_id] = t
    }
  }

  // 出勤中・接客なしのキャスト
  const workingCasts = (shifts as any[]).filter((s: any) => !s.is_absent && s.actual_start && !s.actual_end)
  const idleCasts = workingCasts.filter((s: any) => s.cast_id !== null && !castToTicket[s.cast_id] && !tissueCastIds.has(s.cast_id))
  const busyCasts = workingCasts.filter((s: any) => s.cast_id !== null && castToTicket[s.cast_id!])

  return (
    <div className="flex-1 overflow-y-auto space-y-4 px-1 pb-4">
      {/* 卓ごと */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">卓ごと（{tickets.length}卓）</div>
        {tickets.length === 0 ? (
          <div className="text-xs text-gray-600 py-4 text-center">オープン中の卓はありません</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {tickets.map((t: any) => (
              <div key={t.id}
                className="bg-night-700 rounded-lg p-2"
              >
                <div className="flex items-center justify-between">
                  <button onClick={() => onTicketClick(t.id)}
                    className="text-white font-bold hover:text-primary-300">{t.table_no || '—'}</button>
                  <span className="text-[10px] text-gray-500">{t.guest_count}名</span>
                </div>
                <button onClick={() => onOpenActiveCastsModal(t)}
                  className="block w-full text-left text-xs mt-0.5 hover:bg-night-600 rounded px-1 py-0.5 transition-colors">
                  <span className="text-gray-500">担当: </span>
                  <span className="text-purple-300 underline decoration-dotted">
                    {(t.current_casts && t.current_casts.length > 0)
                      ? t.current_casts.map((c: any) => c.cast_name).join('・')
                      : '未設定'}
                  </span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ティッシュ配り中 */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">ティッシュ配り中（{(activeTissue as any[]).length}名）</div>
        {(activeTissue as any[]).length === 0 ? (
          <div className="text-xs text-gray-600 py-3 text-center">ティッシュ配り中のキャストはいません</div>
        ) : (
          <div className="space-y-1.5">
            {(activeTissue as any[]).map((t: any) => (
              <div key={t.id} className="flex items-center gap-2 bg-amber-900/20 border border-amber-800/50 rounded-lg px-3 py-2">
                <span className="text-white text-sm font-medium flex-1">{t.cast_name}</span>
                <input
                  type="number" min={0} placeholder="枚数"
                  value={tissueCounts[t.id] ?? ''}
                  onChange={e => setTissueCounts(prev => ({ ...prev, [t.id]: e.target.value }))}
                  className="input-field w-20 text-xs py-1 text-center"
                />
                <button onClick={() => completeTissue(t.id)}
                  className="text-xs px-3 py-1 bg-amber-700 hover:bg-amber-600 text-white rounded">完了</button>
                <button onClick={() => cancelTissue(t.id)}
                  className="text-xs px-2 py-1 text-red-400 hover:text-red-300">取消</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* キャストごと */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">出勤中キャスト（{workingCasts.length}名）</div>
        {workingCasts.length === 0 ? (
          <div className="text-xs text-gray-600 py-4 text-center">出勤中のキャストはいません</div>
        ) : (
          <>
            <div className="text-[10px] text-gray-500 mb-1">対応中（{busyCasts.length}名）</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 mb-3">
              {busyCasts.map((s: any) => {
                const t = castToTicket[s.cast_id!]
                return (
                  <button key={s.shift_id}
                    onClick={(e) => {
                      const rect = (e.target as HTMLElement).getBoundingClientRect()
                      setCastActionTarget({ cast_id: s.cast_id, cast_name: s.cast_name, x: rect.left, y: rect.bottom + 4 })
                    }}
                    className="text-left bg-pink-900/30 hover:bg-pink-900/50 border border-pink-800/50 rounded-lg p-2 transition-colors"
                  >
                    <div className="text-white text-sm font-medium">{s.cast_name}</div>
                    <div className="text-[10px] text-pink-300 mt-0.5">{t.table_no} 対応中</div>
                  </button>
                )
              })}
              {busyCasts.length === 0 && (
                <div className="col-span-full text-[10px] text-gray-600 text-center py-2">対応中のキャストはいません</div>
              )}
            </div>
            <div className="text-[10px] text-gray-500 mb-1">待機中（{idleCasts.length}名）</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {idleCasts.map((s: any) => (
                <button key={s.shift_id}
                  onClick={(e) => {
                    const rect = (e.target as HTMLElement).getBoundingClientRect()
                    setCastActionTarget({ cast_id: s.cast_id, cast_name: s.cast_name, x: rect.left, y: rect.bottom + 4 })
                  }}
                  className="text-left bg-night-700 hover:bg-night-600 rounded-lg p-2 transition-colors"
                >
                  <div className="text-gray-300 text-sm font-medium">{s.cast_name}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5">待機中</div>
                </button>
              ))}
              {idleCasts.length === 0 && (
                <div className="col-span-full text-[10px] text-gray-600 text-center py-2">待機中のキャストはいません</div>
              )}
            </div>
          </>
        )}
      </div>

      {/* キャストアクションポップアップ */}
      {castActionTarget && (
        <div className="fixed inset-0 z-50" onClick={() => setCastActionTarget(null)}>
          <div
            className="absolute bg-night-800 border border-gray-700 rounded-xl shadow-2xl py-2 min-w-[180px] max-h-[60vh] overflow-y-auto"
            style={{ left: Math.min(castActionTarget.x, window.innerWidth - 200), top: Math.min(castActionTarget.y, window.innerHeight - 300) }}
            onClick={e => e.stopPropagation()}
          >
            <div className="px-3 py-1 text-xs text-gray-400 border-b border-gray-700 mb-1">
              {castActionTarget.cast_name} の割り当て
            </div>
            <button
              onClick={async () => {
                try {
                  await apiClient.post('/api/tissue/start', { store_id: storeId, cast_ids: [castActionTarget.cast_id] })
                  qc.invalidateQueries({ queryKey: ['tissue-active', storeId] })
                  qc.invalidateQueries({ queryKey: ['casts-working', storeId] })
                  qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
                } catch (e: any) {
                  alert(e?.response?.data?.detail || 'エラー')
                }
                setCastActionTarget(null)
              }}
              className="w-full text-left px-3 py-1.5 text-sm text-amber-400 hover:bg-amber-900/30 transition-colors"
            >
              🧻 ティッシュ配り
            </button>
            {tickets.length > 0 && (
              <div className="border-t border-gray-700 mt-1 pt-1">
                <div className="px-3 py-0.5 text-[10px] text-gray-500">卓に付ける</div>
                {tickets.map((t: any) => (
                  <button
                    key={t.id}
                    onClick={async () => {
                      try {
                        const currentIds = (t.current_casts || []).map((c: any) => c.cast_id).filter((id: number) => id !== castActionTarget.cast_id)
                        currentIds.push(castActionTarget.cast_id)
                        await apiClient.post(`/api/tickets/${t.id}/assignments/set`, { cast_ids: currentIds, assignment_type: 'jounai' })
                        qc.invalidateQueries({ queryKey: ['tickets', storeId, 'open'] })
                        qc.invalidateQueries({ queryKey: ['casts-working', storeId] })
                        qc.invalidateQueries({ queryKey: ['tissue-active', storeId] })
                      } catch (e: any) {
                        alert(e?.response?.data?.detail || 'エラー')
                      }
                      setCastActionTarget(null)
                    }}
                    className="w-full text-left px-3 py-1.5 text-sm text-white hover:bg-night-600 transition-colors flex items-center gap-2"
                  >
                    <span className="text-primary-400 font-bold w-8">{t.table_no}</span>
                    <span className="text-gray-400 text-xs">
                      {(t.current_casts || []).length > 0
                        ? (t.current_casts || []).map((c: any) => c.cast_name).join('・')
                        : '—'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}


function CastAttendanceView({ storeId }: { storeId: number }) {
  const qc = useQueryClient()
  const [showClockIn, setShowClockIn] = useState(false)
  const [clockInTab, setClockInTab] = useState<'normal' | 'help' | 'taiken'>('normal')
  const [taikenName, setTaikenName] = useState('')
  const [q, setQ] = useState('')
  const [helpStoreId, setHelpStoreId] = useState<number | ''>('')
  const [helpCastName, setHelpCastName] = useState('')
  const [now, setNow] = useState(Date.now())

  // 出勤フロー: キャスト選択 → 時刻選択
  const [clockInCast, setClockInCast] = useState<{ id: number; name: string } | null>(null)

  // 退勤フロー: 退勤ボタン → 時刻選択
  const [clockOutShiftId, setClockOutShiftId] = useState<number | null>(null)

  // 時間修正（キャスト）
  const [editingShiftId, setEditingShiftId] = useState<number | null>(null)
  const [editStart, setEditStart] = useState('')
  const [editEnd, setEditEnd] = useState('')
  const [editTarget, setEditTarget] = useState<'start' | 'end' | null>(null)

  // 社員/アルバイト出勤フロー: null=非表示, 'name'=名前入力, 'time'=時刻選択
  const [staffClockInStep, setStaffClockInStep] = useState<null | 'name' | 'time'>(null)
  const [staffClockInName, setStaffClockInName] = useState('')
  // 社員退勤/時間修正
  const [staffClockOutId, setStaffClockOutId] = useState<number | null>(null)
  const [editingStaffId, setEditingStaffId] = useState<number | null>(null)
  const [staffEditStart, setStaffEditStart] = useState('')
  const [staffEditEnd, setStaffEditEnd] = useState('')
  const [staffEditTarget, setStaffEditTarget] = useState<'start' | 'end' | null>(null)

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const { data: working = [] } = useQuery({
    queryKey: ['attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/attendance/working/${storeId}`).then(r => r.data),
    enabled: !!storeId,
    refetchInterval: 30000,
  })

  const { data: staffRecords = [] } = useQuery({
    queryKey: ['staff-attendance', storeId],
    queryFn: () => apiClient.get(`/api/casts/staff-attendance/today/${storeId}`).then(r => r.data),
    enabled: !!storeId,
    refetchInterval: 30000,
  })

  const { data: castsAll = [] } = useQuery({
    queryKey: ['casts', storeId],
    queryFn: () => apiClient.get(`/api/casts/${storeId}`).then(r => r.data),
    enabled: !!storeId,
  })
  const workingCastIds = new Set((working as any[]).filter((w: any) => !w.actual_end).map((w: any) => w.cast_id))
  const filteredCasts = (castsAll as any[]).filter((c: any) =>
    c.is_active && !workingCastIds.has(c.id) && (!q || c.stage_name?.includes(q))
  )

  // 社員/アルバイト mutations
  const staffClockInMutation = useMutation({
    mutationFn: ({ name, time, is_late, is_absent }: { name: string; time: string; is_late?: boolean; is_absent?: boolean }) =>
      apiClient.post('/api/casts/staff-attendance/clock-in', {
        store_id: storeId, name,
        actual_start: is_absent ? undefined : (time || undefined),
        is_late: !!is_late,
        is_absent: !!is_absent,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-attendance', storeId] })
      setStaffClockInStep(null)
      setStaffClockInName('')
    },
  })

  const staffClockOutMutation = useMutation({
    mutationFn: ({ id, time }: { id: number; time: string }) =>
      apiClient.post(`/api/casts/staff-attendance/${id}/clock-out`, { actual_end: time }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-attendance', storeId] })
      setStaffClockOutId(null)
    },
  })

  const staffDeleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/casts/staff-attendance/${id}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['staff-attendance', storeId] }),
    onError: (e: any) => alert(`削除に失敗しました: ${e?.response?.data?.detail ?? e?.message ?? '不明なエラー'}`),
  })

  const staffUpdateTimeMutation = useMutation({
    mutationFn: ({ id, actual_start, actual_end }: { id: number; actual_start?: string; actual_end?: string }) =>
      apiClient.patch(`/api/casts/staff-attendance/${id}/time`, { actual_start, actual_end }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-attendance', storeId] })
      setEditingStaffId(null)
      setStaffEditTarget(null)
    },
  })

  const clockInMutation = useMutation({
    mutationFn: ({ castId, time, is_late, is_absent }: { castId: number; time: string; is_late?: boolean; is_absent?: boolean }) =>
      apiClient.post('/api/casts/attendance/clock-in', {
        cast_id: castId, store_id: storeId,
        actual_start: time || undefined,
        is_late: !!is_late,
        is_absent: !!is_absent,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendance', storeId] })
      setShowClockIn(false)
      setClockInCast(null)
      setQ('')
    },
  })

  const helpClockInMutation = useMutation({
    mutationFn: ({ name, fromStoreId, time }: { name: string; fromStoreId: number; time: string }) =>
      apiClient.post('/api/casts/attendance/help-clock-in', {
        store_id: storeId,
        help_from_store_id: fromStoreId,
        help_cast_name: name,
        actual_start: time || undefined,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendance', storeId] })
      setShowClockIn(false)
      setHelpCastName('')
      setHelpStoreId('')
      setClockInTab('normal')
    },
  })

  const taikenClockInMutation = useMutation({
    mutationFn: ({ name, time, hourlyRate }: { name: string; time: string; hourlyRate: number }) =>
      apiClient.post('/api/casts/attendance/taiken-clock-in', {
        store_id: storeId,
        cast_name: name,
        actual_start: time || undefined,
        hourly_rate: hourlyRate,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendance', storeId] })
      qc.invalidateQueries({ queryKey: ['casts', storeId] })
      setShowClockIn(false)
      setTaikenName('')
      setClockInTab('normal')
    },
  })

  const clockOutMutation = useMutation({
    mutationFn: ({ shiftId, time }: { shiftId: number; time: string }) =>
      apiClient.post(`/api/casts/attendance/${shiftId}/clock-out`, { actual_end: time }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendance', storeId] })
      setClockOutShiftId(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (shiftId: number) => apiClient.post(`/api/casts/attendance/${shiftId}/remove`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['attendance', storeId] }),
    onError: (e: any) => alert(`削除に失敗しました: ${e?.response?.data?.detail ?? e?.message ?? '不明なエラー'}`),
  })

  const updateTimeMutation = useMutation({
    mutationFn: ({ shiftId, actual_start, actual_end }: { shiftId: number; actual_start?: string; actual_end?: string }) =>
      apiClient.patch(`/api/casts/attendance/${shiftId}/time`, { actual_start, actual_end }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendance', storeId] })
      setEditingShiftId(null)
      setEditTarget(null)
    },
  })

  // ISO → 実際の HH:MM（バックエンド送信用・TIME_SLOTS の value と対応）
  const isoToActual = (iso: string) => {
    const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
    const jst = new Date(d.getTime() + 9 * 3600 * 1000)
    return `${jst.getUTCHours().toString().padStart(2, '0')}:${jst.getUTCMinutes().toString().padStart(2, '0')}`
  }

  // ISO → バー表記（表示用: 00:30 → 24:30）
  const isoToBarDisp = (iso: string) => toBarDisplay(isoToActual(iso))

  // 現在時刻を30分刻みで丸めた実HH:MM
  const nowHhmm = () => {
    const jst = new Date(Date.now() + 9 * 3600 * 1000)
    const h = jst.getUTCHours(), m = jst.getUTCMinutes()
    return `${h.toString().padStart(2, '0')}:${m < 30 ? '00' : '30'}`
  }

  const fmtElapsed = (startIso: string) => {
    const startMs = new Date(startIso.endsWith('Z') ? startIso : startIso + 'Z').getTime()
    const sec = Math.floor((now - startMs) / 1000)
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    const s = sec % 60
    return h > 0
      ? `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
      : `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  // キャストカード共通レンダラ
  const renderCastCard = (w: any) => (
    <div key={w.shift_id} className="bg-gray-900 border border-gray-700 rounded-xl px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-white font-medium text-sm">{w.cast_name}</span>
            {w.is_absent
              ? <span className="text-xs px-1.5 py-0.5 bg-red-900/60 text-red-400 rounded">当欠</span>
              : w.actual_end
                ? <span className="text-xs px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded">退勤済み</span>
                : <span className="text-xs px-1.5 py-0.5 bg-emerald-900/60 text-emerald-400 rounded">勤務中</span>
            }
            {w.is_late && !w.is_absent && (
              <span className="text-xs px-1.5 py-0.5 bg-yellow-900/60 text-yellow-400 rounded">遅刻</span>
            )}
            {w.taiken_status === 'taiken' && (
              <select
                value=""
                onChange={async (e) => {
                  const val = e.target.value
                  if (!val) return
                  const labels: Record<string, string> = { honnyuu: '本入店', fusaiyou: '不採用', sai_taiken: '再体入' }
                  if (!confirm(`${w.cast_name} を「${labels[val]}」に変更しますか？`)) return
                  try {
                    await apiClient.post(`/api/casts/${w.cast_id}/taiken-status`, { status: val })
                    qc.invalidateQueries({ queryKey: ['attendance', storeId] })
                    qc.invalidateQueries({ queryKey: ['casts', storeId] })
                  } catch (err: any) { alert(err?.response?.data?.detail || 'エラー') }
                }}
                className="text-[10px] px-1 py-0.5 bg-pink-900/60 text-pink-300 rounded border border-pink-700 cursor-pointer"
              >
                <option value="">体入中</option>
                <option value="honnyuu">本入店</option>
                <option value="fusaiyou">不採用</option>
                <option value="sai_taiken">再体入</option>
              </select>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {w.is_absent ? '当欠' : <>
              出勤 {w.actual_start ? isoToBarDisp(w.actual_start) : '—'}
              {w.actual_end && <> → 退勤 {isoToBarDisp(w.actual_end)}</>}
            </>}
          </div>
        </div>
        {!w.actual_end && !w.is_absent && w.actual_start && (
          <div className="text-xs font-mono text-emerald-400 shrink-0">{fmtElapsed(w.actual_start)}</div>
        )}
      </div>
      <div className="flex gap-1.5">
        <button onClick={() => { setEditingShiftId(w.shift_id); setEditStart(w.actual_start ? isoToActual(w.actual_start) : ''); setEditEnd(w.actual_end ? isoToActual(w.actual_end) : ''); setEditTarget(null) }}
          className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors">
          時間修正
        </button>
        <button onClick={() => setClockOutShiftId(w.shift_id)}
          disabled={!!w.actual_end || !!w.is_absent}
          className="text-xs px-2 py-1 bg-gray-700 hover:bg-blue-800/70 text-gray-300 hover:text-blue-300 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
          退勤
        </button>
        <button onClick={() => deleteMutation.mutate(w.shift_id)}
          disabled={deleteMutation.isPending}
          className="text-xs px-2 py-1 bg-gray-700 hover:bg-red-800/70 text-gray-300 hover:text-red-300 rounded-lg transition-colors disabled:opacity-40">
          削除
        </button>
      </div>
      {editingShiftId === w.shift_id && (
        <div className="border-t border-gray-700 pt-2 space-y-2">
          <div className="flex gap-2">
            <button onClick={() => setEditTarget('start')}
              className="flex-1 text-left px-2 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors">
              <div className="text-xs text-gray-500">出勤</div>
              <div className="text-sm text-white font-mono">{editStart ? toBarDisplay(editStart) : '未設定'}</div>
            </button>
            <button onClick={() => setEditTarget('end')}
              className="flex-1 text-left px-2 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors">
              <div className="text-xs text-gray-500">退勤</div>
              <div className="text-sm text-white font-mono">{editEnd ? toBarDisplay(editEnd) : '未設定'}</div>
            </button>
          </div>
          <div className="flex gap-1.5 justify-end">
            <button onClick={() => updateTimeMutation.mutate({ shiftId: w.shift_id, actual_start: editStart || undefined, actual_end: editEnd || undefined })}
              disabled={!editStart || updateTimeMutation.isPending}
              className="text-xs px-3 py-1 bg-primary-700 hover:bg-primary-600 text-white rounded-lg disabled:opacity-40 transition-colors">確定</button>
            <button onClick={() => { setEditingShiftId(null); setEditTarget(null) }}
              className="text-xs px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-400 rounded-lg transition-colors">キャンセル</button>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="flex gap-4 min-h-0">

        {/* 左: 社員/アルバイト勤怠 */}
        <div className="flex-1 min-w-0 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-white">社員/アルバイト勤怠</h2>
            <button onClick={() => setStaffClockInStep('name')}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-blue-700 hover:bg-blue-600 text-white text-xs rounded-lg transition-colors">
              <Plus className="w-3.5 h-3.5" />出勤
            </button>
          </div>
          {(staffRecords as any[]).length === 0 ? (
            <div className="text-gray-600 text-xs text-center py-12">記録はありません</div>
          ) : (
            <div className="space-y-2">
              {(staffRecords as any[]).map((r: any) => (
                <div key={r.id} className="bg-gray-900 border border-gray-700 rounded-xl px-3 py-2.5 space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-white font-medium text-sm">{r.name}</span>
                        {r.is_absent
                          ? <span className="text-xs px-1.5 py-0.5 bg-red-900/60 text-red-400 rounded">当欠</span>
                          : r.actual_end
                            ? <span className="text-xs px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded">退勤済み</span>
                            : <span className="text-xs px-1.5 py-0.5 bg-blue-900/60 text-blue-400 rounded">勤務中</span>
                        }
                        {r.is_late && !r.is_absent && (
                          <span className="text-xs px-1.5 py-0.5 bg-yellow-900/60 text-yellow-400 rounded">遅刻</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {r.is_absent ? '当欠' : <>
                          出勤 {r.actual_start ? isoToBarDisp(r.actual_start) : '—'}
                          {r.actual_end && <> → 退勤 {isoToBarDisp(r.actual_end)}</>}
                        </>}
                      </div>
                    </div>
                    {!r.actual_end && !r.is_absent && r.actual_start && (
                      <div className="text-xs font-mono text-blue-400 shrink-0">{fmtElapsed(r.actual_start)}</div>
                    )}
                  </div>
                  <div className="flex gap-1.5">
                    <button onClick={() => { setEditingStaffId(r.id); setStaffEditStart(r.actual_start ? isoToActual(r.actual_start) : ''); setStaffEditEnd(r.actual_end ? isoToActual(r.actual_end) : ''); setStaffEditTarget(null) }}
                      className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors">
                      時間修正
                    </button>
                    <button onClick={() => setStaffClockOutId(r.id)}
                      disabled={!!r.actual_end || !!r.is_absent}
                      className="text-xs px-2 py-1 bg-gray-700 hover:bg-blue-800/70 text-gray-300 hover:text-blue-300 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                      退勤
                    </button>
                    <button onClick={() => staffDeleteMutation.mutate(r.id)}
                      disabled={staffDeleteMutation.isPending}
                      className="text-xs px-2 py-1 bg-gray-700 hover:bg-red-800/70 text-gray-300 hover:text-red-300 rounded-lg transition-colors disabled:opacity-40">
                      削除
                    </button>
                  </div>
                  {editingStaffId === r.id && (
                    <div className="border-t border-gray-700 pt-2 space-y-2">
                      <div className="flex gap-2">
                        <button onClick={() => setStaffEditTarget('start')}
                          className="flex-1 text-left px-2 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors">
                          <div className="text-xs text-gray-500">出勤</div>
                          <div className="text-sm text-white font-mono">{staffEditStart ? toBarDisplay(staffEditStart) : '未設定'}</div>
                        </button>
                        <button onClick={() => setStaffEditTarget('end')}
                          className="flex-1 text-left px-2 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors">
                          <div className="text-xs text-gray-500">退勤</div>
                          <div className="text-sm text-white font-mono">{staffEditEnd ? toBarDisplay(staffEditEnd) : '未設定'}</div>
                        </button>
                      </div>
                      <div className="flex gap-1.5 justify-end">
                        <button onClick={() => staffUpdateTimeMutation.mutate({ id: r.id, actual_start: staffEditStart || undefined, actual_end: staffEditEnd || undefined })}
                          disabled={!staffEditStart || staffUpdateTimeMutation.isPending}
                          className="text-xs px-3 py-1 bg-primary-700 hover:bg-primary-600 text-white rounded-lg disabled:opacity-40 transition-colors">確定</button>
                        <button onClick={() => { setEditingStaffId(null); setStaffEditTarget(null) }}
                          className="text-xs px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-400 rounded-lg transition-colors">キャンセル</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 右: キャスト勤怠 */}
        <div className="flex-1 min-w-0 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-white">キャスト勤怠 <span className="text-emerald-400 text-xs ml-1">{(working as any[]).filter((w: any) => !w.actual_end && !w.is_absent).length}名勤務中</span></h2>
            <button onClick={() => setShowClockIn(true)}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded-lg transition-colors">
              <Plus className="w-3.5 h-3.5" />出勤
            </button>
          </div>
          {(working as any[]).length === 0 ? (
            <div className="text-gray-600 text-xs text-center py-12">本日の出勤記録はありません</div>
          ) : (
            <div className="space-y-2">
              {(working as any[]).map(renderCastCard)}
            </div>
          )}
        </div>
      </div>

      {/* 出勤: キャスト検索モーダル */}
      {showClockIn && !clockInCast && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={() => { setShowClockIn(false); setQ(''); setClockInTab('normal'); setHelpCastName(''); setHelpStoreId(''); setTaikenName('') }}>
          <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center">
              <h3 className="font-bold text-white">出勤キャストを選択</h3>
              <button onClick={() => { setShowClockIn(false); setQ(''); setClockInTab('normal'); setHelpCastName(''); setHelpStoreId(''); setTaikenName('') }}><X className="w-5 h-5 text-gray-400" /></button>
            </div>
            {/* タブ */}
            <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
              <button onClick={() => setClockInTab('normal')}
                className={`flex-1 text-xs py-1 rounded-md transition-colors ${clockInTab === 'normal' ? 'bg-emerald-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                通常出勤
              </button>
              <button onClick={() => setClockInTab('help')}
                className={`flex-1 text-xs py-1 rounded-md transition-colors ${clockInTab === 'help' ? 'bg-blue-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                ヘルプ出勤
              </button>
              <button onClick={() => setClockInTab('taiken')}
                className={`flex-1 text-xs py-1 rounded-md transition-colors ${clockInTab === 'taiken' ? 'bg-pink-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                体験入店
              </button>
            </div>

            {clockInTab === 'normal' ? (
              <>
                <input type="text" value={q} onChange={e => setQ(e.target.value)}
                  placeholder="キャスト名で検索" className="input-field w-full text-sm" autoFocus />
                <div className="space-y-1 max-h-72 overflow-y-auto">
                  {filteredCasts.map((c: any) => (
                    <button key={c.id} onClick={() => setClockInCast({ id: c.id, name: c.stage_name })}
                      className="w-full text-left px-3 py-2.5 rounded-lg bg-gray-800 hover:bg-emerald-900/50 text-gray-200 hover:text-emerald-300 transition-colors">
                      <span className="font-medium">{c.stage_name}</span>
                    </button>
                  ))}
                  {filteredCasts.length === 0 && (
                    <p className="text-center text-gray-500 text-sm py-4">{q ? '該当なし' : '全員出勤中です'}</p>
                  )}
                </div>
              </>
            ) : clockInTab === 'help' ? (
              <HelpClockInForm
                storeId={storeId}
                helpStoreId={helpStoreId}
                setHelpStoreId={setHelpStoreId}
                helpCastName={helpCastName}
                setHelpCastName={setHelpCastName}
                onSubmit={(name, fromStoreId, time) => helpClockInMutation.mutate({ name, fromStoreId, time })}
                onCancel={() => { setShowClockIn(false); setClockInTab('normal'); setHelpCastName(''); setHelpStoreId('') }}
                isPending={helpClockInMutation.isPending}
              />
            ) : (
              <TaikenClockInForm
                taikenName={taikenName}
                setTaikenName={setTaikenName}
                onSubmit={(name, time, hourlyRate) => taikenClockInMutation.mutate({ name, time, hourlyRate })}
                onCancel={() => { setShowClockIn(false); setClockInTab('normal'); setTaikenName('') }}
                isPending={taikenClockInMutation.isPending}
              />
            )}
          </div>
        </div>
      )}

      {clockInCast && (
        <TimePickerModal title={`${clockInCast.name} の出勤時間`} defaultValue={nowHhmm()} showStatusTabs={true}
          onSelect={(time, opts) => clockInMutation.mutate({ castId: clockInCast.id, time, ...opts })}
          onClose={() => { setClockInCast(null); setShowClockIn(false); setQ('') }} />
      )}
      {clockOutShiftId !== null && (
        <TimePickerModal title="退勤時間を選択" defaultValue={nowHhmm()}
          onSelect={time => clockOutMutation.mutate({ shiftId: clockOutShiftId, time })}
          onClose={() => setClockOutShiftId(null)} />
      )}
      {editTarget === 'start' && (
        <TimePickerModal title="出勤時間を選択" defaultValue={editStart || nowHhmm()}
          onSelect={time => { setEditStart(time); setEditTarget(null) }}
          onClose={() => setEditTarget(null)} />
      )}
      {editTarget === 'end' && (
        <TimePickerModal title="退勤時間を選択" defaultValue={editEnd || nowHhmm()}
          onSelect={time => { setEditEnd(time); setEditTarget(null) }}
          onClose={() => setEditTarget(null)} />
      )}
      {/* 社員/アルバイト出勤: 名前入力ステップ */}
      {staffClockInStep === 'name' && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={() => { setStaffClockInStep(null); setStaffClockInName('') }}>
          <div className="card w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center">
              <h3 className="font-bold text-white">社員/アルバイト 出勤登録</h3>
              <button onClick={() => { setStaffClockInStep(null); setStaffClockInName('') }}><X className="w-5 h-5 text-gray-400" /></button>
            </div>
            <input type="text" value={staffClockInName} onChange={e => setStaffClockInName(e.target.value)}
              placeholder="従業員名を入力" className="input-field w-full text-sm" autoFocus
              onKeyDown={e => { if (e.key === 'Enter' && staffClockInName.trim()) setStaffClockInStep('time') }} />
            <button
              disabled={!staffClockInName.trim()}
              onClick={() => { if (staffClockInName.trim()) setStaffClockInStep('time') }}
              className="w-full btn-primary disabled:opacity-40">
              次へ（時刻を選択）
            </button>
          </div>
        </div>
      )}
      {/* 社員/アルバイト出勤: 時刻選択ステップ */}
      {staffClockInStep === 'time' && (
        <TimePickerModal
          title={`${staffClockInName} の出勤時間`}
          defaultValue={nowHhmm()}
          showStatusTabs={true}
          onSelect={(time, opts) => staffClockInMutation.mutate({ name: staffClockInName.trim(), time, ...opts })}
          onClose={() => { setStaffClockInStep(null); setStaffClockInName('') }}
        />
      )}
      {staffClockOutId !== null && (
        <TimePickerModal title="退勤時間を選択" defaultValue={nowHhmm()}
          onSelect={time => staffClockOutMutation.mutate({ id: staffClockOutId, time })}
          onClose={() => setStaffClockOutId(null)} />
      )}
      {staffEditTarget === 'start' && (
        <TimePickerModal title="出勤時間を選択" defaultValue={staffEditStart || nowHhmm()}
          onSelect={time => { setStaffEditStart(time); setStaffEditTarget(null) }}
          onClose={() => setStaffEditTarget(null)} />
      )}
      {staffEditTarget === 'end' && (
        <TimePickerModal title="退勤時間を選択" defaultValue={staffEditEnd || nowHhmm()}
          onSelect={time => { setStaffEditEnd(time); setStaffEditTarget(null) }}
          onClose={() => setStaffEditTarget(null)} />
      )}
    </div>
  )
}


// ─────────────────────────────────────────
// 日報一覧
// ─────────────────────────────────────────
function SessionReportList({ storeId }: { storeId: number }) {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [openTicketId, setOpenTicketId] = useState<number | null>(null)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['session-list', storeId],
    queryFn: () => apiClient.get('/api/sessions/list', { params: { store_id: storeId, limit: 60 } }).then(r => r.data),
    enabled: !!storeId,
  })
  const selected = sessions.find((s: any) => s.id === selectedId) ?? null
  const { data: sessionTickets = [] } = useQuery({
    queryKey: ['session-tickets', selected?.id],
    queryFn: () => apiClient.get(`/api/sessions/${selected.id}/tickets`).then(r => r.data),
    enabled: !!selected?.id,
  })
  const { data: castDrinks = [] } = useQuery({
    queryKey: ['session-cast-drinks', selected?.id],
    queryFn: () => apiClient.get(`/api/sessions/${selected!.id}/cast-drinks`).then(r => r.data),
    enabled: !!selected?.id,
  })
  const { data: staffAttendanceReport = [] } = useQuery({
    queryKey: ['session-staff-attendance', selected?.id],
    queryFn: () => apiClient.get(`/api/sessions/${selected!.id}/staff-attendance`).then(r => r.data),
    enabled: !!selected?.id,
  })

  const DENOM_LABELS: Record<number, string> = {
    10000: '壱万円', 5000: '五千円', 2000: '二千円', 1000: '千円',
    500: '五百円', 100: '百円', 50: '五十円', 10: '十円', 5: '五円', 1: '一円',
  }

  return (
    <>
    <div className="flex flex-1 min-h-0 gap-3">
      {/* 一覧 */}
      <div className="w-72 shrink-0 overflow-y-auto space-y-1.5 pr-1">
        {isLoading && <div className="text-gray-500 text-sm text-center py-8">読み込み中...</div>}
        {!isLoading && sessions.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">日報データがありません</div>
        )}
        {sessions.map((s: any) => {
          const diff = s.cash_diff
          const isSel = selected?.id === s.id
          return (
            <button key={s.id} onClick={() => setSelectedId(s.id)}
              className={`w-full text-left rounded-xl px-3 py-2.5 border transition-colors ${isSel ? 'border-blue-500 bg-blue-900/30' : 'border-gray-700 bg-gray-900 hover:bg-gray-800'}`}>
              <div className="flex justify-between items-center">
                <span className="font-bold text-white text-sm">{s.date}</span>
                {diff != null && diff !== 0 && (
                  <span className={`text-xs font-medium ${diff > 0 ? 'text-blue-300' : 'text-red-400'}`}>
                    {diff > 0 ? '+' : ''}¥{diff.toLocaleString()}
                  </span>
                )}
                {diff === 0 && <span className="text-xs text-yellow-400 font-bold">PERFECT</span>}
              </div>
              <div className="text-xs text-gray-400 mt-0.5 flex gap-2">
                {s.operator_name && <span>{s.operator_name}</span>}
                <span className="text-green-400">売上 ¥{(s.sales_snapshot || 0).toLocaleString()}</span>
              </div>
            </button>
          )
        })}
      </div>

      {/* 詳細 */}
      <div className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="text-gray-500 text-sm text-center py-16">左のリストから日報を選択してください</div>
        ) : (
          <div className="space-y-4 max-w-2xl">
            {/* ヘッダー */}
            <div className="flex items-baseline gap-3">
              <h2 className="text-xl font-black text-white">{selected.date} 日報</h2>
              {selected.event_name && <span className="text-pink-400 text-sm">{selected.event_name}</span>}
            </div>

            {/* 日報スナップショット（Phase D） */}
            <DailyReportPanel storeId={storeId} date={selected.date} onTicketClick={(id) => setOpenTicketId(id)} />

            {/* サマリー */}
            <div className="grid grid-cols-2 gap-3">
              <div className="card space-y-2">
                <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1">営業情報</div>
                <Row label="担当者" value={selected.operator_name || '—'} />
                <Row label="開始時刻" value={selected.opened_at ? fmtIsoToJstTime(selected.opened_at) : '—'} />
                <Row label="終了時刻" value={selected.closed_at ? fmtIsoToJstTime(selected.closed_at) : '—'} />
                <Row label="開始オペレーター" value={selected.opened_by_name || '—'} />
                <Row label="終了オペレーター" value={selected.closed_by_name || '—'} />
                {selected.notes && <Row label="メモ" value={selected.notes} />}
              </div>
              <div className="card space-y-2">
                <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1">売上・レジ</div>
                <Row label="本日売上" value={`¥${(selected.sales_snapshot || 0).toLocaleString()}`} highlight="green" />
                <Row label="開始レジ金" value={`¥${(selected.opening_cash || 0).toLocaleString()}`} />
                <Row label="終了レジ金" value={`¥${(selected.closing_cash || 0).toLocaleString()}`} />
                <Row label="前日過不足金" value={selected.prev_day_diff ? `${selected.prev_day_diff > 0 ? '+' : ''}¥${selected.prev_day_diff.toLocaleString()}` : '±¥0'} />
                {selected.cash_diff != null ? (
                  <Row
                    label="当日過不足金"
                    value={selected.cash_diff === 0 ? 'PERFECT! ±¥0' : `${selected.cash_diff > 0 ? '+' : ''}¥${selected.cash_diff.toLocaleString()}`}
                    highlight={selected.cash_diff === 0 ? 'yellow' : selected.cash_diff > 0 ? 'blue' : 'red'}
                  />
                ) : null}
              </div>
            </div>

            {/* 金種明細 */}
            {(selected.opening_cash_detail || selected.closing_cash_detail) && (
              <div className="card">
                <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">金種明細</div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500">
                      <th className="text-left py-0.5">金種</th>
                      <th className="text-right py-0.5">開始（枚）</th>
                      <th className="text-right py-0.5">終了（枚）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[10000,5000,2000,1000,500,100,50,10,5,1].map(d => {
                      const open = selected.opening_cash_detail?.[String(d)] || 0
                      const close = selected.closing_cash_detail?.[String(d)] || 0
                      if (open === 0 && close === 0) return null
                      return (
                        <tr key={d} className="border-t border-gray-800">
                          <td className="py-0.5 text-gray-300">{DENOM_LABELS[d]} ({d.toLocaleString()})</td>
                          <td className="py-0.5 text-right text-gray-400">{open > 0 ? open : '—'}</td>
                          <td className="py-0.5 text-right text-white">{close > 0 ? close : '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* 決済内訳 */}
            {(selected.cash_sales != null || selected.card_sales != null || selected.code_sales != null) && (
              <div className="card space-y-2">
                <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1">決済内訳</div>
                {selected.cash_sales != null && <Row label="現金決済" value={`¥${(selected.cash_sales).toLocaleString()}`} />}
                {selected.card_sales != null && <Row label="カード決済" value={`¥${(selected.card_sales).toLocaleString()}`} highlight="blue" />}
                {selected.code_sales != null && <Row label="コード決済" value={`¥${(selected.code_sales).toLocaleString()}`} highlight="blue" />}
              </div>
            )}

            {/* 経費・出金 */}
            {selected.expenses_detail && (
              <div className="card space-y-3">
                <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1">経費・出金</div>
                {(selected.expenses_detail.liquor || []).filter((e: any) => e.amount > 0).length > 0 && (
                  <div>
                    <div className="text-xs text-orange-400 mb-1">酒類経費</div>
                    {(selected.expenses_detail.liquor || []).filter((e: any) => e.amount > 0).map((e: any, i: number) => (
                      <div key={i} className="flex justify-between text-xs py-0.5 border-t border-gray-800">
                        <span className="text-gray-300">{e.category || '—'}</span>
                        <span className="text-white">¥{e.amount.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
                {(selected.expenses_detail.other || []).filter((e: any) => e.amount > 0).length > 0 && (
                  <div>
                    <div className="text-xs text-orange-400 mb-1">その他経費</div>
                    {(selected.expenses_detail.other || []).filter((e: any) => e.amount > 0).map((e: any, i: number) => (
                      <div key={i} className="flex justify-between text-xs py-0.5 border-t border-gray-800">
                        <span className="text-gray-300">{e.category || '—'}</span>
                        <span className="text-white">¥{e.amount.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
                {(selected.expenses_detail.withdrawals || []).filter((w: any) => w.amount > 0).length > 0 && (
                  <div>
                    <div className="text-xs text-orange-400 mb-1">出金名目</div>
                    {(selected.expenses_detail.withdrawals || []).filter((w: any) => w.amount > 0).map((w: any, i: number) => (
                      <div key={i} className="flex justify-between text-xs py-0.5 border-t border-gray-800">
                        <span className="text-gray-300">{w.name || '—'}</span>
                        <span className="text-white">¥{w.amount.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>
        )}
      </div>
    </div>
    {openTicketId && (
      <TicketDetailModal ticketId={openTicketId} storeId={storeId} onClose={() => setOpenTicketId(null)} />
    )}
    </>
  )
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: 'green' | 'red' | 'blue' | 'yellow' }) {
  const cls = highlight === 'green' ? 'text-green-400' : highlight === 'red' ? 'text-red-400' : highlight === 'blue' ? 'text-blue-300' : highlight === 'yellow' ? 'text-yellow-400 font-bold' : 'text-white'
  return (
    <div className="flex justify-between items-start gap-2">
      <span className="text-xs text-gray-500 shrink-0">{label}</span>
      <span className={`text-xs text-right ${cls}`}>{value}</span>
    </div>
  )
}

function fmtIsoToJstTime(isoStr: string): string {
  const d = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z')
  const jst = new Date(d.getTime() + 9 * 3600 * 1000)
  return `${jst.getUTCHours().toString().padStart(2,'0')}:${jst.getUTCMinutes().toString().padStart(2,'0')}`
}
