import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import apiClient from '../api/client'

export default function Dashboard() {
  const { stores } = useAuthStore()
  const navigate = useNavigate()

  const { data: birthdays = [] } = useQuery({
    queryKey: ['birthdays-dashboard'],
    queryFn: () => apiClient.get('/api/customers/birthdays/upcoming', { params: { days: 7 } }).then(r => r.data),
    staleTime: 1000 * 60 * 30,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">ダッシュボード</h1>
        <p className="text-gray-400 mt-1 text-sm">
          {new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
        </p>
      </div>

      {/* 誕生日アラート */}
      {birthdays.length > 0 && (
        <div style={{ backgroundColor: '#422006', border: '1px solid #854d0e', borderRadius: '16px', padding: '12px 16px' }}>
          <p className="text-yellow-400 text-sm font-medium mb-2">🎂 今週の誕生日</p>
          <div className="flex flex-wrap gap-2">
            {birthdays.map((b: any) => (
              <button
                key={b.id}
                onClick={() => navigate(`/customers/${b.id}`)}
                className="text-xs bg-yellow-900/50 text-yellow-300 px-3 py-1 rounded-full hover:bg-yellow-900 transition-colors"
              >
                {b.name} — {b.days_until === 0 ? '今日！🎉' : `あと${b.days_until}日`}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {stores.map((store) => (
          <StoreSummaryCard key={store.id} storeId={store.id} storeName={store.name} />
        ))}
      </div>

      {stores.length === 0 && (
        <div className="text-gray-500 text-center py-12">
          店舗データを読み込み中...
        </div>
      )}
    </div>
  )
}

function StoreSummaryCard({ storeId, storeName }: { storeId: number; storeName: string }) {
  const { data } = useQuery({
    queryKey: ['live', storeId],
    queryFn: () => apiClient.get(`/api/tickets/live/${storeId}`).then((r) => r.data),
    refetchInterval: 30000,
  })

  return (
    <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '16px', padding: '16px' }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-white text-lg">{storeName}</h3>
        <span className="text-xs font-bold px-2 py-1 rounded-full bg-pink-900 text-pink-300">営業中</span>
      </div>
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">会計済み売上</span>
          <span className="text-white font-medium">¥{(data?.closed_amount ?? 0).toLocaleString()}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">未会計（{data?.open_count ?? 0}卓）</span>
          <span className="text-yellow-400 font-medium">¥{(data?.open_amount ?? 0).toLocaleString()}</span>
        </div>
        <div style={{ borderTop: '1px solid #374151', paddingTop: '8px', marginTop: '8px' }} className="flex justify-between">
          <span className="text-gray-300 font-medium">合計</span>
          <span className="text-white font-bold text-xl">¥{(data?.total_amount ?? 0).toLocaleString()}</span>
        </div>
      </div>
    </div>
  )
}
