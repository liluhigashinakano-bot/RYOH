import { useQueries } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import apiClient from '../api/client'

export default function Dashboard() {
  const { stores } = useAuthStore()
  const navigate = useNavigate()

  const { data: birthdays = [] } = useQueries({
    queries: [{
      queryKey: ['birthdays-dashboard'],
      queryFn: () => apiClient.get('/api/customers/birthdays/upcoming', { params: { days: 7 } }).then(r => r.data),
      staleTime: 1000 * 60 * 30,
    }],
  })[0] as any

  const dashQueries = useQueries({
    queries: stores.map(s => ({
      queryKey: ['dashboard', s.id],
      queryFn: () => apiClient.get(`/api/sessions/dashboard/${s.id}`).then(r => r.data),
      refetchInterval: 30000,
      retry: 1,
    })),
  })

  return (
    <div className="space-y-5">
      {/* ヘッダー */}
      <div>
        <h1 className="text-2xl font-bold text-white">リアルタイム状況</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          {new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
        </p>
      </div>

      {/* 誕生日アラート */}
      {(birthdays as any[]).length > 0 && (
        <div style={{ backgroundColor: '#422006', border: '1px solid #854d0e', borderRadius: '12px', padding: '10px 14px' }}>
          <p className="text-yellow-400 text-xs font-medium mb-2">今週の誕生日</p>
          <div className="flex flex-wrap gap-2">
            {(birthdays as any[]).map((b: any) => (
              <button
                key={b.id}
                onClick={() => navigate(`/customers/${b.id}`)}
                className="text-xs bg-yellow-900/50 text-yellow-300 px-3 py-1 rounded-full hover:bg-yellow-900 transition-colors"
              >
                {b.name} — {b.days_until === 0 ? '今日！' : `あと${b.days_until}日`}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 店舗ごとのセクション */}
      {stores.map((store, i) => {
        const q = dashQueries[i]
        const dash = q.data as any
        const isLoading = q.isLoading
        const isError = q.isError
        const isOpen = !!dash?.session

        return (
          <div key={store.id} className="space-y-3">
            {/* 店舗名ヘッダー */}
            <div className="flex items-center gap-3 border-b border-gray-800 pb-2">
              <h2 className="text-white font-bold text-lg">{store.name}</h2>
              {!isLoading && !isError && (
                <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                  isOpen ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-500'
                }`}>
                  {isOpen ? '● 営業中' : '営業外'}
                </span>
              )}
              {isOpen && dash.session?.operator_name && (
                <span className="text-gray-500 text-xs">担当: {dash.session.operator_name}</span>
              )}
              {isOpen && dash.session?.event_name && (
                <span className="text-pink-400 text-xs font-medium">{dash.session.event_name}</span>
              )}
            </div>

            {isError ? (
              <p className="text-red-400 text-sm py-2">取得エラー</p>
            ) : isLoading || !dash ? (
              <p className="text-gray-600 text-sm py-2">読み込み中...</p>
            ) : (
              <>
                {/* 売上グリッド */}
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  <StatCard label="会計済み売上" value={`¥${(dash.closed_sales ?? 0).toLocaleString()}`} valueClass="text-white text-lg font-bold" />
                  <StatCard label="未会計売上" value={`¥${(dash.open_sales ?? 0).toLocaleString()}`} valueClass="text-yellow-400 text-lg font-bold" />
                  <StatCard
                    label="本日合計"
                    value={`¥${((dash.closed_sales ?? 0) + (dash.open_sales ?? 0)).toLocaleString()}`}
                    valueClass="text-white text-lg font-bold"
                  />
                  <StatCard label="会計済み組数" value={`${dash.closed_groups ?? 0} 組`} valueClass="text-white font-bold" />
                  <StatCard label="会計済み人数" value={`${dash.closed_guests ?? 0} 人`} valueClass="text-white font-bold" />
                  <StatCard label="未会計組数 / 人数" value={`${dash.open_groups ?? 0}組 ${dash.open_guests ?? 0}人`} valueClass="text-yellow-400 font-bold" />
                </div>

                {/* スタッフ・キャスト */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <PersonnelCard title="勤務中スタッフ" list={dash.working_staff ?? []} renderItem={(s: any) => (
                    <div key={s.name} className="flex items-center justify-between py-1.5">
                      <div className="flex items-center gap-2">
                        {s.is_late && <span className="text-xs bg-red-900/60 text-red-300 px-1.5 py-0.5 rounded">遅</span>}
                        <span className="text-white text-sm">{s.name}</span>
                      </div>
                      <span className="text-gray-400 text-xs">{s.actual_start}</span>
                    </div>
                  )} />
                  <PersonnelCard title="勤務中キャスト" list={dash.working_casts ?? []} renderItem={(c: any) => (
                    <div key={c.cast_id} className="flex items-center justify-between py-1.5">
                      <div className="flex items-center gap-2">
                        {c.is_late && <span className="text-xs bg-red-900/60 text-red-300 px-1.5 py-0.5 rounded">遅</span>}
                        <span className="text-white text-sm">{c.stage_name}</span>
                        {c.rank && <span className="text-xs text-gray-500">{c.rank}</span>}
                      </div>
                      <span className="text-gray-400 text-xs">{c.actual_start}</span>
                    </div>
                  )} />
                </div>
              </>
            )}
          </div>
        )
      })}

      {stores.length === 0 && (
        <div className="text-gray-500 text-center py-16 text-sm">店舗データを読み込み中...</div>
      )}
    </div>
  )
}

function StatCard({ label, value, valueClass }: { label: string; value: string; valueClass: string }) {
  return (
    <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '12px', padding: '12px 14px' }}>
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={valueClass}>{value}</p>
    </div>
  )
}

function PersonnelCard({ title, list, renderItem }: { title: string; list: any[]; renderItem: (item: any) => JSX.Element }) {
  return (
    <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '12px', padding: '12px 14px' }}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-gray-300 text-sm font-medium">{title}</p>
        <span className="text-xs text-gray-500">{list.length}名</span>
      </div>
      {list.length === 0 ? (
        <p className="text-gray-600 text-xs py-1">なし</p>
      ) : (
        <div className="divide-y divide-gray-800">
          {list.map(renderItem)}
        </div>
      )}
    </div>
  )
}
