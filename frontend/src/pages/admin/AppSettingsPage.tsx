import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

export default function AppSettingsPage() {
  const { stores } = useAuthStore()
  const qc = useQueryClient()

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-white">設定</h1>

      <div className="card">
        <h2 className="text-sm font-bold text-white mb-3">AI機能設定</h2>
        <div className="space-y-3">
          {stores.map(store => (
            <StoreAIToggle key={store.id} store={store} />
          ))}
        </div>
      </div>
    </div>
  )
}

function StoreAIToggle({ store }: { store: any }) {
  const qc = useQueryClient()
  const { data: storeDetail } = useQuery({
    queryKey: ['store', store.id],
    queryFn: () => apiClient.get(`/api/stores/${store.id}`).then(r => r.data),
  })

  const mutation = useMutation({
    mutationFn: (enabled: boolean) =>
      apiClient.put(`/api/stores/${store.id}`, { ai_advisor_enabled: enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['store', store.id] })
      qc.invalidateQueries({ queryKey: ['stores'] })
    },
  })

  const enabled = storeDetail?.ai_advisor_enabled ?? true

  return (
    <div className="flex items-center justify-between bg-gray-800 rounded-lg px-4 py-3">
      <div>
        <div className="text-white text-sm font-medium">{store.name}</div>
        <div className="text-gray-500 text-xs">付け回しAIアドバイス</div>
      </div>
      <button
        onClick={() => mutation.mutate(!enabled)}
        disabled={mutation.isPending}
        className={`relative w-12 h-6 rounded-full transition-colors ${enabled ? 'bg-pink-600' : 'bg-gray-600'}`}
      >
        <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${enabled ? 'left-6' : 'left-0.5'}`} />
      </button>
    </div>
  )
}
