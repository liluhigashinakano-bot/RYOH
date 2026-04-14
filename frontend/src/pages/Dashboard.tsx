import { useQueries, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Trophy } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import apiClient from '../api/client'
import axios from 'axios'

// 天気コード → アイコン・説明
const WMO_CODES: Record<number, { icon: string; label: string }> = {
  0: { icon: '☀️', label: '快晴' }, 1: { icon: '🌤️', label: '晴れ' }, 2: { icon: '⛅', label: '曇り時々晴れ' }, 3: { icon: '☁️', label: '曇り' },
  45: { icon: '🌫️', label: '霧' }, 48: { icon: '🌫️', label: '霧氷' },
  51: { icon: '🌦️', label: '弱い霧雨' }, 53: { icon: '🌦️', label: '霧雨' }, 55: { icon: '🌧️', label: '強い霧雨' },
  61: { icon: '🌧️', label: '弱い雨' }, 63: { icon: '🌧️', label: '雨' }, 65: { icon: '🌧️', label: '強い雨' },
  71: { icon: '🌨️', label: '弱い雪' }, 73: { icon: '🌨️', label: '雪' }, 75: { icon: '❄️', label: '強い雪' },
  80: { icon: '🌦️', label: 'にわか雨' }, 81: { icon: '🌧️', label: 'にわか雨' }, 82: { icon: '⛈️', label: '激しいにわか雨' },
  95: { icon: '⛈️', label: '雷雨' }, 96: { icon: '⛈️', label: '雹を伴う雷雨' }, 99: { icon: '⛈️', label: '激しい雷雨' },
}

// 店舗ごとの座標 + 関連路線（フォールバック用、DB設定優先）
const STORE_META_FALLBACK: Record<string, {
  lat: number; lon: number
  relatedLines: string[]
}> = {
  higashinakano: { lat: 35.7075, lon: 139.6782, relatedLines: ['中央総武線', '中央線(快速)', '総武線(快速)', '都営大江戸線'] },
  shinnakano: { lat: 35.6975, lon: 139.6615, relatedLines: ['東京メトロ丸ノ内線'] },
  honancho: { lat: 35.6835, lon: 139.6480, relatedLines: ['東京メトロ丸ノ内線'] },
}

function getStoreMeta(store: any) {
  const fb = STORE_META_FALLBACK[store.code] || null
  return {
    lat: store.latitude ?? fb?.lat,
    lon: store.longitude ?? fb?.lon,
    relatedLines: (store.related_lines as string[]) ?? fb?.relatedLines ?? [],
  }
}

function useWeather(lat: number, lon: number) {
  return useQuery({
    queryKey: ['weather', lat, lon],
    queryFn: async () => {
      const r = await axios.get('https://api.open-meteo.com/v1/forecast', {
        params: {
          latitude: lat, longitude: lon,
          hourly: 'temperature_2m,weathercode,precipitation_probability,windspeed_10m',
          timezone: 'Asia/Tokyo',
          forecast_days: 2,
        },
      })
      return r.data
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
  })
}

function parseWeatherHours(weather: any) {
  if (!weather?.hourly) return []
  const hourly = weather.hourly
  const now = new Date()
  // 現在時刻以降の最初のインデックスを探す（日付込みで比較）
  const startIdx = hourly.time.findIndex((t: string) => new Date(t) >= now)
  if (startIdx < 0) return []
  return hourly.time.slice(startIdx, startIdx + 8).map((_: any, i: number) => {
    const idx = startIdx + i
    if (idx >= hourly.time.length) return null
    const code = hourly.weathercode[idx] ?? 0
    const wmo = WMO_CODES[code] || { icon: '❓', label: '不明' }
    const h = new Date(hourly.time[idx]).getHours()
    return {
      hour: h,
      hourLabel: `${h}時`,
      temp: Math.round(hourly.temperature_2m[idx]),
      icon: wmo.icon,
      label: wmo.label,
      rain: hourly.precipitation_probability[idx] ?? 0,
      wind: Math.round(hourly.windspeed_10m[idx]),
    }
  }).filter(Boolean)
}

function StoreWeatherTrain({ store, trainData, lastTrains }: { store: any; trainData: any[]; lastTrains: any[] }) {
  const meta = getStoreMeta(store)
  if (!meta.lat || !meta.lon) return null

  const { data: weather } = useWeather(meta.lat, meta.lon)
  const hours = parseWeatherHours(weather)
  const current = hours[0]
  const rainyHours = hours.filter((h: any) => h.rain >= 40)

  // この店舗に関連する路線の運行情報（部分一致）
  const storeTrains = trainData.filter(t => meta.relatedLines.some(rl => t.line.includes(rl) || rl.includes(t.line)))
  const storeLastTrains = lastTrains.filter((t: any) => t.store === store.code && t.arrive)

  return (
    <div className="space-y-1 pt-1 border-t border-gray-800/60">
      {/* 天気 */}
      {current && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-lg">{current.icon}</span>
          <span className="text-white font-bold">{current.temp}°C</span>
          <span className="text-gray-400">{current.label}</span>
          <span className="text-gray-500">風{current.wind}km/h</span>
          {current.rain > 0 && <span className="text-blue-400">{current.rain}%</span>}
        </div>
      )}
      {rainyHours.length > 0 && (
        <div className="text-[10px] text-blue-400 bg-blue-900/20 border border-blue-800/40 rounded px-2 py-0.5">
          🌧️ {rainyHours.map((h: any) => `${h.hour}時(${h.rain}%)`).join(' ')}
        </div>
      )}
      {hours.length > 0 && (
        <div className="flex gap-0.5 overflow-x-auto pb-0.5">
          {hours.map((h: any, i: number) => (
            <div key={i} className="flex flex-col items-center min-w-[36px] text-[9px]">
              <span className="text-gray-500">{h.hour}時</span>
              <span className="text-sm">{h.icon}</span>
              <span className="text-white">{h.temp}°</span>
              {h.rain > 0 && <span className="text-blue-400">{h.rain}%</span>}
              <span className="text-gray-600">{h.wind}</span>
            </div>
          ))}
        </div>
      )}

      {/* 鉄道運行情報 + 終電到着 */}
      {(storeTrains.length > 0 || storeLastTrains.length > 0) && (
        <div className="flex items-center gap-2 flex-wrap text-[10px]">
          {storeTrains.filter(t => t.status !== 'normal').map(t => (
            <span key={t.line} className="flex items-center gap-1">
              <span className="text-gray-400">🚃{t.line.replace('JR', '').replace('東京メトロ', '').replace('都営', '')}</span>
              <span className={t.status === 'delay' ? 'text-yellow-400' : 'text-red-400'}>
                {t.status === 'delay' ? '⚠️遅延' : '🚫運休'}
              </span>
              {t.detail && <span className="text-gray-500 max-w-[200px] truncate">{t.detail}</span>}
            </span>
          ))}
          {storeLastTrains.map((lt: any) => {
            const now = new Date(); const h = now.getHours(); const m = now.getMinutes()
            const nowMin = (h < 5 ? h + 24 : h) * 60 + m
            const [th, tm] = lt.arrive.split(':').map(Number)
            const remaining = (th < 5 ? th + 24 : th) * 60 + tm - nowMin
            const isPast = remaining < 0
            const isUrgent = remaining >= 0 && remaining <= 30
            return (
              <span key={`${lt.from}-${lt.to}`} className="text-gray-400">
                🚃{lt.from}→{lt.to}
                <span className={`ml-0.5 font-mono ${isPast ? 'text-gray-600' : isUrgent ? 'text-red-400 font-bold' : 'text-gray-300'}`}>{lt.arrive}着</span>
                {isUrgent && <span className="text-red-400 ml-0.5">({remaining}分)</span>}
                {isPast && <span className="text-gray-600 ml-0.5">終</span>}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { stores: authStores } = useAuthStore()
  const navigate = useNavigate()

  // ダッシュボードでは全店舗を表示
  const { data: allStoresData } = useQuery({
    queryKey: ['stores-all'],
    queryFn: () => apiClient.get('/api/stores', { params: { all: true } }).then(r => r.data),
    staleTime: 1000 * 60 * 10,
  })
  const stores = (allStoresData as any[]) ?? authStores

  const birthdayQuery = useQueries({
    queries: [{
      queryKey: ['birthdays-dashboard'],
      queryFn: () => apiClient.get('/api/customers/birthdays/upcoming', { params: { days: 7 } }).then(r => r.data),
      staleTime: 1000 * 60 * 30,
    }],
  })[0]
  const birthdays: any[] = (birthdayQuery.data as any[]) ?? []

  // 鉄道運行情報（全店舗共通、5分キャッシュ）
  const { data: trainInfo } = useQuery({
    queryKey: ['train-info'],
    queryFn: () => apiClient.get('/api/train-info').then(r => r.data),
    staleTime: 1000 * 60 * 5,
    refetchInterval: 1000 * 60 * 5,
  })
  const trainData: any[] = (trainInfo as any)?.lines ?? []
  const lastTrainsData: any[] = (trainInfo as any)?.last_trains ?? []

  const dashQueries = useQueries({
    queries: stores.map(s => ({
      queryKey: ['dashboard', s.id],
      queryFn: () => apiClient.get(`/api/sessions/dashboard/${s.id}`).then(r => r.data),
      refetchInterval: 30000,
      retry: 1,
    })),
  })

  // 売上トップ店舗（データ取得済みの店舗の中で最大。同額首位は先頭のみ）
  const topStoreId = (() => {
    let maxTotal = -1
    let topId: number | null = null
    dashQueries.forEach((q, i) => {
      const d = q.data as any
      if (!d) return
      const total = (d.closed_sales ?? 0) + (d.open_sales ?? 0)
      if (total > maxTotal) { maxTotal = total; topId = stores[i].id }
    })
    return topId
  })()

  // 月間ランキング（1位表示用）
  const today2 = new Date()
  const { data: rankings } = useQuery({
    queryKey: ['monthly-rankings', today2.getFullYear(), today2.getMonth() + 1],
    queryFn: () => apiClient.get('/api/reports/monthly-rankings', {
      params: { year: today2.getFullYear(), month: today2.getMonth() + 1 }
    }).then(r => r.data),
    staleTime: 1000 * 60 * 5,
    refetchInterval: 1000 * 60 * 5,
  })

  return (
    <div className="space-y-3">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white">リアルタイム情報</h1>
          <p className="text-gray-500 text-xs">
            {new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
          </p>
        </div>
      </div>

      {/* 月間ランキング（各指標の1位店舗） */}
      {rankings && (() => {
        const renderItem = (stripPrefix?: string) => ([key, r]: [string, any]) => {
          const tops: any[] = r.tops || []
          const v = tops[0]?.value
          const fmtV = v == null ? '—' : r.format === 'yen'
            ? `¥${Number(v).toLocaleString()}`
            : Number(v).toLocaleString()
          const names = tops.map((t: any) => t.store_name).join('・') || '—'
          const label = stripPrefix && r.label.startsWith(stripPrefix) ? r.label.slice(stripPrefix.length) : r.label
          return (
            <div key={key} className="bg-gray-900/60 rounded px-2 py-1 text-[11px] flex items-center justify-between gap-2">
              <span className="text-gray-400 truncate">{label}</span>
              <span className="text-right shrink-0">
                <span className="text-yellow-300 font-bold">{names}</span>
                <span className="text-white ml-1">{fmtV}</span>
              </span>
            </div>
          )
        }
        const entries = Object.entries(rankings.rankings as Record<string, any>)
        const DRINK_TOTAL_KEYS = new Set([
          'drink_l_total', 'drink_mg_total', 'shot_cast_total',
          'champagne_count', 'champagne_amount',
        ])
        const perSet = entries.filter(([k]) => k.includes('_per_set'))
        const drinkTotals = entries.filter(([k]) => DRINK_TOTAL_KEYS.has(k))
        const general = entries.filter(([k]) => !k.includes('_per_set') && !DRINK_TOTAL_KEYS.has(k))
        return (
          <div className="rounded-xl border border-yellow-900/40 px-3 py-2 space-y-2" style={{ backgroundColor: '#1a1206' }}>
            <div className="text-yellow-400 text-xs font-medium flex items-center gap-1">
              🏆 今月の1位（{rankings.year}年{rankings.month}月 / 月初〜現在）
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5">
              {general.map(renderItem())}
            </div>
            {drinkTotals.length > 0 && (
              <>
                <div className="text-yellow-400/70 text-[10px] font-medium pt-1 border-t border-yellow-900/40">ドリンク・シャンパン合計</div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-1.5">
                  {drinkTotals.map(renderItem())}
                </div>
              </>
            )}
            {perSet.length > 0 && (
              <>
                <div className="text-yellow-400/70 text-[10px] font-medium pt-1 border-t border-yellow-900/40">1セットあたり</div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-1.5">
                  {perSet.map(renderItem('1セットあたり'))}
                </div>
              </>
            )}
            {(rankings.cast_incentive_top3 as any[])?.length > 0 && (
              <>
                <div className="text-yellow-400/70 text-[10px] font-medium pt-1 border-t border-yellow-900/40">キャスト部門 — インセンティブTOP3（全店）</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-1.5">
                  {(rankings.cast_incentive_top3 as any[]).map((c: any, i: number) => (
                    <div key={`${c.cast_id ?? c.cast_name}-${i}`} className="bg-gray-900/60 rounded px-2 py-1 text-[11px] flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        <span className="text-yellow-400 font-bold">{['🥇','🥈','🥉'][i]}</span>
                        <span className="text-white font-medium">{c.cast_name}{c.is_help && <span className="text-blue-300 text-[10px] ml-0.5">[ヘルプ]</span>}</span>
                        <span className="text-gray-500 text-[10px]">{c.store_name}</span>
                      </span>
                      <span className="text-pink-300 font-bold">¥{Number(c.incentive_total).toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )
      })()}

      {/* 誕生日アラート */}
      {birthdays.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap px-3 py-2 rounded-lg" style={{ backgroundColor: '#422006', border: '1px solid #854d0e' }}>
          <span className="text-yellow-400 text-xs font-medium shrink-0">今週の誕生日:</span>
          {birthdays.map((b: any) => (
            <button key={b.id} onClick={() => navigate(`/customers/${b.id}`)}
              className="text-xs bg-yellow-900/50 text-yellow-300 px-2 py-0.5 rounded-full hover:bg-yellow-900 transition-colors">
              {b.name} {b.days_until === 0 ? '今日！' : `あと${b.days_until}日`}
            </button>
          ))}
        </div>
      )}

      {/* 店舗一覧 */}
      <div className="space-y-2">
        {stores.map((store, i) => {
          const q = dashQueries[i]
          const dash = q.data as any
          const isLoading = q.isLoading
          const isError = q.isError
          const isOpen = !!dash?.session

          return (
            <div key={store.id} className="rounded-xl border border-gray-800 overflow-hidden" style={{ backgroundColor: '#0f172a' }}>
              {/* 店舗名行 */}
              <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-800/60" style={{ backgroundColor: '#1e293b' }}>
                <span className="font-bold text-white text-sm">{store.name}</span>
                {topStoreId === store.id && (
                  <Trophy className="w-4 h-4 text-yellow-400 animate-bounce" />
                )}
                {!isLoading && !isError && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${isOpen ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-500'}`}>
                    {isOpen ? '● 営業中' : '営業外'}
                  </span>
                )}
                {isOpen && dash.session?.operator_name && (
                  <span className="text-gray-500 text-xs">{dash.session.operator_name}</span>
                )}
                {isOpen && dash.session?.event_name && (
                  <span className="text-pink-400 text-xs">{dash.session.event_name}</span>
                )}
              </div>

              {isError ? (
                <p className="text-red-400 text-xs px-3 py-2">取得エラー</p>
              ) : isLoading || !dash ? (
                <p className="text-gray-600 text-xs px-3 py-2">読み込み中...</p>
              ) : (
                <div className="px-3 py-1.5 space-y-1">
                  {/* 総売上（会計済 + 未会計） */}
                  <div className="flex items-baseline gap-2">
                    <span className="text-gray-500 text-xs">総売上</span>
                    <span className="text-red-500 font-bold text-lg">¥{((dash.closed_sales ?? 0) + (dash.open_sales ?? 0)).toLocaleString()}</span>
                    <span className="text-[10px] text-gray-500">{(dash.closed_groups ?? 0) + (dash.open_groups ?? 0)}組/{(dash.closed_guests ?? 0) + (dash.open_guests ?? 0)}名</span>
                  </div>
                  {/* 売上内訳 */}
                  <div className="flex items-center gap-3 flex-wrap text-xs">
                    <span><span className="text-gray-500">会計済 </span><span className="text-white font-bold">¥{(dash.closed_sales ?? 0).toLocaleString()}</span><span className="text-[10px] text-gray-500 ml-1">{dash.closed_groups ?? 0}組/{dash.closed_guests ?? 0}名</span></span>
                    <span><span className="text-gray-500">未会計 </span><span className="text-yellow-400 font-bold">¥{(dash.open_sales ?? 0).toLocaleString()}</span><span className="text-[10px] text-yellow-500/80 ml-1">{dash.open_groups ?? 0}組/{dash.open_guests ?? 0}名</span></span>
                  </div>

                  {/* スタッフ・キャスト行 */}
                  <div className="flex items-center gap-4 flex-wrap text-xs">
                    <span>
                      <span className="text-gray-500">スタッフ </span>
                      {(dash.working_staff ?? []).length === 0
                        ? <span className="text-gray-700">なし</span>
                        : <span className="text-white">{(dash.working_staff as any[]).map((s: any) => s.name).join('、')}</span>}
                    </span>
                    <span>
                      <span className="text-gray-500">キャスト </span>
                      {(dash.working_casts ?? []).length === 0
                        ? <span className="text-gray-700">なし</span>
                        : <span className="text-white">{(dash.working_casts as any[]).map((c: any) => c.stage_name).join('、')}</span>}
                    </span>
                  </div>

                  {/* ドリンク・シャンパン・カスタムドリンク */}
                  <div className="flex items-center gap-3 flex-wrap text-xs pt-1 border-t border-gray-800/60">
                    <div><span className="text-gray-500">S </span><span className="text-white font-bold">{dash.drink_s_total ?? 0}</span></div>
                    <div><span className="text-gray-500">L </span><span className="text-white font-bold">{dash.drink_l_total ?? 0}</span></div>
                    <div><span className="text-gray-500">MG </span><span className="text-white font-bold">{dash.drink_mg_total ?? 0}</span></div>
                    <div><span className="text-gray-500">SH </span><span className="text-white font-bold">{dash.shot_cast_total ?? 0}</span></div>
                    {(dash.custom_drink_columns ?? []).map((col: any) => (
                      <div key={col.short}>
                        <span className="text-gray-500">{col.label} </span>
                        <span className="text-white font-bold">{(dash.custom_drinks_total ?? {})[col.short] ?? 0}</span>
                      </div>
                    ))}
                    <div>
                      <span className="text-gray-500">ｼｬﾝﾊﾟﾝ </span>
                      <span className="text-yellow-400 font-bold">{dash.champagne_count ?? 0}本</span>
                      <span className="text-yellow-400 font-bold ml-1">¥{(dash.champagne_amount ?? 0).toLocaleString()}</span>
                    </div>
                  </div>

                  {/* 天気 + 鉄道（店舗ごと） */}
                  <StoreWeatherTrain store={store} trainData={trainData} lastTrains={lastTrainsData} />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {stores.length === 0 && (
        <div className="text-gray-500 text-center py-8 text-sm">読み込み中...</div>
      )}
    </div>
  )
}
