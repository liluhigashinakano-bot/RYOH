import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

export default function AppSettingsPage() {
  const { stores } = useAuthStore()

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-white">設定</h1>

      {stores.map(store => (
        <StoreSettings key={store.id} store={store} />
      ))}
    </div>
  )
}

function Toggle({ enabled, onToggle, disabled }: { enabled: boolean; onToggle: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      className={`relative w-12 h-6 rounded-full transition-colors shrink-0 ${enabled ? 'bg-pink-600' : 'bg-gray-600'}`}
    >
      <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${enabled ? 'left-6' : 'left-0.5'}`} />
    </button>
  )
}

function StoreSettings({ store }: { store: any }) {
  const qc = useQueryClient()
  const { data: storeDetail } = useQuery({
    queryKey: ['store', store.id],
    queryFn: () => apiClient.get(`/api/stores/${store.id}`).then(r => r.data),
  })

  const mutation = useMutation({
    mutationFn: (data: Record<string, any>) =>
      apiClient.put(`/api/stores/${store.id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['store', store.id] })
      qc.invalidateQueries({ queryKey: ['stores'] })
    },
  })

  const aiEnabled = storeDetail?.ai_advisor_enabled ?? true
  const manualSetStart = storeDetail?.manual_set_start ?? true

  return (
    <div className="card space-y-3">
      <h2 className="text-sm font-bold text-white">{store.name}</h2>

      <div className="flex items-center justify-between bg-gray-800 rounded-lg px-4 py-3">
        <div>
          <div className="text-white text-sm">付け回しAIアドバイス</div>
          <div className="text-gray-500 text-xs">OFFにするとボタンがグレーアウト</div>
        </div>
        <Toggle enabled={aiEnabled} onToggle={() => mutation.mutate({ ai_advisor_enabled: !aiEnabled })} disabled={mutation.isPending} />
      </div>

      <div className="flex items-center justify-between bg-gray-800 rounded-lg px-4 py-3">
        <div>
          <div className="text-white text-sm">伝票開始ボタン</div>
          <div className="text-gray-500 text-xs">
            {manualSetStart
              ? 'ON: 伝票開始ボタンを手動で押してカウント開始'
              : 'OFF: 新規伝票作成と同時にカウント自動開始'}
          </div>
        </div>
        <Toggle enabled={manualSetStart} onToggle={() => mutation.mutate({ manual_set_start: !manualSetStart })} disabled={mutation.isPending} />
      </div>
    </div>
  )
}
