import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import apiClient from '../api/client'

export default function Dashboard() {
  const { stores } = useAuthStore()
  const navigate = useNavigate()
  const [selectedStoreId, setSelectedStoreId] = useState<number | null>(null)

  const storeId = selectedStoreId ?? stores[0]?.id ?? null
  const store = stores.find(s => s.id === storeId)

  const { data: birthdays = [] } = useQuery({
    queryKey: ['birthdays-dashboard'],
    queryFn: () => apiClient.get('/api/customers/birthdays/upcoming', { params: { days: 7 } }).then(r => r.data),
    staleTime: 1000 * 60 * 30,
  })

  const { data: dash, isLoading, isError, error } = useQuery({
    queryKey: ['dashboard', storeId],
    queryFn: () => apiClient.get(`/api/sessions/dashboard/${storeId}`).then(r => r.data),
    refetchInterval: 30000,
    enabled: storeId !== null,
    retry: 1,
  })

  const isOpen = !!dash?.session

  return (
    <div className="space-y-5">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">リアルタイム状況</h1>
          <p className="text-gray-400 text-sm mt-0.5">
            {new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
          </p>
        </div>
        {/* 店舗タブ */}
        {stores.length > 1 && (
          <div className="flex gap-1">
            {stores.map(s => (
              <button
                key={s.id}
                onClick={() => setSelectedStoreId(s.id)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  s.id === storeId
                    ? 'bg-pink-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 誕生日アラート */}
      {birthdays.length > 0 && (
        <div style={{ backgroundColor: '#422006', border: '1px solid #854d0e', borderRadius: '12px', padding: '10px 14px' }}>
          <p className="text-yellow-400 text-xs font-medium mb-2">今週の誕生日</p>
          <div className="flex flex-wrap gap-2">
            {birthdays.map((b: any) => (
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

      {isError ? (
        <div className="text-red-400 text-center py-16 text-sm">
          データ取得エラー: {(error as any)?.response?.data?.detail || (error as any)?.message || '不明なエラー'}
        </div>
      ) : isLoading || !dash ? (
        <div className="text-gray-500 text-center py-16 text-sm">読み込み中...</div>
      ) : (
        <>
          {/* 営業状態バッジ */}
          <div className="flex items-center gap-3">
            <span className={`text-xs font-bold px-3 py-1 rounded-full ${
              isOpen ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-400'
            }`}>
              {isOpen ? '● 営業中' : '営業外'}
            </span>
            {isOpen && dash.session?.operator_name && (
              <span className="text-gray-400 text-xs">担当: {dash.session.operator_name}</span>
            )}
            {isOpen && dash.session?.event_name && (
              <span className="text-pink-400 text-xs font-medium">{dash.session.event_name}</span>
            )}
          </div>

          {/* 売上サマリー 2×3 グリッド */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard
              label="会計済み売上"
              value={`¥${(dash.closed_sales ?? 0).toLocaleString()}`}
              valueClass="text-white text-xl font-bold"
            />
            <StatCard
              label="未会計売上"
              value={`¥${(dash.open_sales ?? 0).toLocaleString()}`}
              valueClass="text-yellow-400 text-xl font-bold"
            />
            <StatCard
              label="会計済み組数"
              value={`${dash.closed_groups ?? 0} 組`}
              valueClass="text-white text-xl font-bold"
            />
            <StatCard
              label="会計済み人数"
              value={`${dash.closed_guests ?? 0} 人`}
              valueClass="text-white text-xl font-bold"
            />
            <StatCard
              label="未会計組数"
              value={`${dash.open_groups ?? 0} 組`}
              valueClass="text-yellow-400 text-xl font-bold"
            />
            <StatCard
              label="未会計人数"
              value={`${dash.open_guests ?? 0} 人`}
              valueClass="text-yellow-400 text-xl font-bold"
            />
          </div>

          {/* 合計 */}
          <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '12px', padding: '14px 16px' }}
               className="flex justify-between items-center">
            <span className="text-gray-300 text-sm font-medium">本日合計売上（会計済み＋未会計）</span>
            <span className="text-white text-2xl font-bold">
              ¥{((dash.closed_sales ?? 0) + (dash.open_sales ?? 0)).toLocaleString()}
            </span>
          </div>

          {/* スタッフ・キャスト */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* 勤務中社員/アルバイト */}
            <PersonnelCard title="勤務中スタッフ" list={dash.working_staff ?? []} renderItem={(s: any) => (
              <div key={s.name} className="flex items-center justify-between py-1.5">
                <div className="flex items-center gap-2">
                  {s.is_late && (
                    <span className="text-xs bg-red-900/60 text-red-300 px-1.5 py-0.5 rounded">遅</span>
                  )}
                  <span className="text-white text-sm">{s.name}</span>
                </div>
                <span className="text-gray-400 text-xs">{s.actual_start}</span>
              </div>
            )} />

            {/* 勤務中キャスト */}
            <PersonnelCard title="勤務中キャスト" list={dash.working_casts ?? []} renderItem={(c: any) => (
              <div key={c.cast_id} className="flex items-center justify-between py-1.5">
                <div className="flex items-center gap-2">
                  {c.is_late && (
                    <span className="text-xs bg-red-900/60 text-red-300 px-1.5 py-0.5 rounded">遅</span>
                  )}
                  <span className="text-white text-sm">{c.stage_name}</span>
                  {c.rank && (
                    <span className="text-xs text-gray-500">{c.rank}</span>
                  )}
                </div>
                <span className="text-gray-400 text-xs">{c.actual_start}</span>
              </div>
            )} />
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, valueClass }: { label: string; value: string; valueClass: string }) {
  return (
    <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '12px', padding: '14px 16px' }}>
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={valueClass}>{value}</p>
    </div>
  )
}

function PersonnelCard({ title, list, renderItem }: { title: string; list: any[]; renderItem: (item: any) => JSX.Element }) {
  return (
    <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '12px', padding: '14px 16px' }}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-gray-300 text-sm font-medium">{title}</p>
        <span className="text-xs text-gray-500">{list.length}名</span>
      </div>
      {list.length === 0 ? (
        <p className="text-gray-600 text-xs py-2">なし</p>
      ) : (
        <div className="divide-y divide-gray-800">
          {list.map(renderItem)}
        </div>
      )}
    </div>
  )
}
