import { useQueries, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
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

function WeatherWidget() {
  const { data: weather, isLoading } = useQuery({
    queryKey: ['weather-forecast'],
    queryFn: async () => {
      const r = await axios.get('https://api.open-meteo.com/v1/forecast', {
        params: {
          latitude: 35.7075,
          longitude: 139.6782,
          hourly: 'temperature_2m,weathercode,precipitation_probability,windspeed_10m,precipitation',
          timezone: 'Asia/Tokyo',
          forecast_days: 1,
        },
      })
      return r.data
    },
    staleTime: 1000 * 60 * 15, // 15分キャッシュ
    refetchInterval: 1000 * 60 * 15,
  })

  if (isLoading || !weather) return null

  const hourly = weather.hourly
  const nowHour = new Date().getHours()
  // 現在時刻から先の時間帯のみ表示（最大12時間）
  const startIdx = hourly.time.findIndex((t: string) => {
    const h = new Date(t).getHours()
    return h >= nowHour
  })
  const hours = hourly.time.slice(startIdx, startIdx + 12).map((_: any, i: number) => {
    const idx = startIdx + i
    const code = hourly.weathercode[idx] ?? 0
    const wmo = WMO_CODES[code] || { icon: '❓', label: '不明' }
    return {
      hour: new Date(hourly.time[idx]).getHours(),
      temp: Math.round(hourly.temperature_2m[idx]),
      icon: wmo.icon,
      label: wmo.label,
      rain: hourly.precipitation_probability[idx] ?? 0,
      precip: hourly.precipitation[idx] ?? 0,
      wind: Math.round(hourly.windspeed_10m[idx]),
    }
  })

  // 現在の天気
  const current = hours[0]
  // 今後の降水あり時間
  const rainyHours = hours.filter((h: any) => h.rain >= 40)

  return (
    <div className="rounded-xl border border-gray-800 overflow-hidden" style={{ backgroundColor: '#0f172a' }}>
      <div className="px-3 py-2 border-b border-gray-800/60 flex items-center gap-2" style={{ backgroundColor: '#1e293b' }}>
        <span className="text-sm font-bold text-white">天気予報</span>
        <span className="text-gray-500 text-xs">中野区</span>
      </div>
      <div className="px-3 py-2 space-y-1.5">
        {/* 現在 */}
        {current && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-2xl">{current.icon}</span>
            <span className="text-white font-bold text-sm">{current.temp}°C</span>
            <span className="text-gray-400">{current.label}</span>
            <span className="text-gray-500">風速{current.wind}km/h</span>
            {current.rain > 0 && <span className="text-blue-400">降水{current.rain}%</span>}
          </div>
        )}
        {/* 降雨アラート */}
        {rainyHours.length > 0 && (
          <div className="text-xs text-blue-400 bg-blue-900/20 border border-blue-800/40 rounded px-2 py-1">
            🌧️ {rainyHours.map((h: any) => `${h.hour}時(${h.rain}%)`).join('、')} に雨の可能性
          </div>
        )}
        {/* 1時間ごと */}
        <div className="flex gap-1 overflow-x-auto pb-1">
          {hours.map((h: any, i: number) => (
            <div key={i} className="flex flex-col items-center min-w-[40px] text-[10px]">
              <span className="text-gray-500">{h.hour}時</span>
              <span className="text-base">{h.icon}</span>
              <span className="text-white">{h.temp}°</span>
              {h.rain > 0 && <span className="text-blue-400">{h.rain}%</span>}
              <span className="text-gray-600">{h.wind}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { stores } = useAuthStore()
  const navigate = useNavigate()

  const birthdayQuery = useQueries({
    queries: [{
      queryKey: ['birthdays-dashboard'],
      queryFn: () => apiClient.get('/api/customers/birthdays/upcoming', { params: { days: 7 } }).then(r => r.data),
      staleTime: 1000 * 60 * 30,
    }],
  })[0]
  const birthdays: any[] = (birthdayQuery.data as any[]) ?? []

  const dashQueries = useQueries({
    queries: stores.map(s => ({
      queryKey: ['dashboard', s.id],
      queryFn: () => apiClient.get(`/api/sessions/dashboard/${s.id}`).then(r => r.data),
      refetchInterval: 30000,
      retry: 1,
    })),
  })

  return (
    <div className="space-y-3">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white">リアルタイム状況</h1>
          <p className="text-gray-500 text-xs">
            {new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
          </p>
        </div>
      </div>

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

      {/* 天気予報 */}
      <WeatherWidget />

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
                  {/* 売上行 */}
                  <div className="flex items-center gap-3 flex-wrap text-xs">
                    <span><span className="text-gray-500">会計済 </span><span className="text-white font-bold">¥{(dash.closed_sales ?? 0).toLocaleString()}</span><span className="text-[10px] text-gray-500 ml-1">{dash.closed_groups ?? 0}組/{dash.closed_guests ?? 0}名</span></span>
                    <span><span className="text-gray-500">未会計 </span><span className="text-yellow-400 font-bold">¥{(dash.open_sales ?? 0).toLocaleString()}</span><span className="text-[10px] text-yellow-500/80 ml-1">{dash.open_groups ?? 0}組/{dash.open_guests ?? 0}名</span></span>
                    <span><span className="text-gray-500">合計 </span><span className="text-white font-bold">¥{((dash.closed_sales ?? 0) + (dash.open_sales ?? 0)).toLocaleString()}</span><span className="text-[10px] text-gray-500 ml-1">{(dash.closed_groups ?? 0) + (dash.open_groups ?? 0)}組/{(dash.closed_guests ?? 0) + (dash.open_guests ?? 0)}名</span></span>
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
