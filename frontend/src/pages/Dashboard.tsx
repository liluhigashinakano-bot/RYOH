import { useQueries } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import apiClient from '../api/client'

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
                <div className="px-3 py-2 space-y-2">
                  {/* 売上行 */}
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">会計済</span>
                      <p className="text-white font-bold">¥{(dash.closed_sales ?? 0).toLocaleString()}</p>
                      <p className="text-[10px] text-gray-500">{dash.closed_groups ?? 0}組 / {dash.closed_guests ?? 0}名</p>
                    </div>
                    <div>
                      <span className="text-gray-500">未会計</span>
                      <p className="text-yellow-400 font-bold">¥{(dash.open_sales ?? 0).toLocaleString()}</p>
                      <p className="text-[10px] text-yellow-500/80">{dash.open_groups ?? 0}組 / {dash.open_guests ?? 0}名</p>
                    </div>
                    <div>
                      <span className="text-gray-500">合計</span>
                      <p className="text-white font-bold">¥{((dash.closed_sales ?? 0) + (dash.open_sales ?? 0)).toLocaleString()}</p>
                      <p className="text-[10px] text-gray-500">{(dash.closed_groups ?? 0) + (dash.open_groups ?? 0)}組 / {(dash.closed_guests ?? 0) + (dash.open_guests ?? 0)}名</p>
                    </div>
                  </div>

                  {/* スタッフ・キャスト行 */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">勤務中スタッフ</span>
                      {(dash.working_staff ?? []).length === 0
                        ? <p className="text-gray-700">なし</p>
                        : <p className="text-white">{(dash.working_staff as any[]).map((s: any) => s.name).join('、')}</p>
                      }
                    </div>
                    <div>
                      <span className="text-gray-500">勤務中キャスト</span>
                      {(dash.working_casts ?? []).length === 0
                        ? <p className="text-gray-700">なし</p>
                        : <p className="text-white">{(dash.working_casts as any[]).map((c: any) => c.stage_name).join('、')}</p>
                      }
                    </div>
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
