import { useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot, Plus, ArrowLeft, Edit2, Trash2, X, Save, AlertCircle, Camera, User, Link, Unlink, Search } from 'lucide-react'
import apiClient from '../../api/client'

export default function CustomerDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [activeTab, setActiveTab] = useState<'info' | 'notes' | 'history'>('info')
  const photoRef = useRef<HTMLInputElement>(null)
  const [showMergeSearch, setShowMergeSearch] = useState(false)
  const [mergeQuery, setMergeQuery] = useState('')

  const uploadPhoto = async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    await apiClient.post(`/api/customers/${id}/photo`, fd)
    qc.invalidateQueries({ queryKey: ['customer', id] })
    qc.invalidateQueries({ queryKey: ['customers'] })
  }

  const { data: customer, isLoading } = useQuery({
    queryKey: ['customer', id],
    queryFn: () => apiClient.get(`/api/customers/${id}`).then(r => r.data),
  })

  const { data: notes = [] } = useQuery({
    queryKey: ['customer-notes', id],
    queryFn: () => apiClient.get(`/api/customers/${id}/notes`).then(r => r.data),
  })

  const addNote = useMutation({
    mutationFn: () => apiClient.post(`/api/customers/${id}/notes`, { note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['customer-notes', id] }); setNote('') },
  })

  const deleteNote = useMutation({
    mutationFn: (noteId: number) => apiClient.delete(`/api/customers/${id}/notes/${noteId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['customer-notes', id] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => apiClient.delete(`/api/customers/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['customers'] }); navigate('/customers') },
  })

  const mergeMutation = useMutation({
    mutationFn: (sourceId: number) => apiClient.post(`/api/customers/${id}/merge`, { source_id: sourceId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['customer', id] })
      qc.invalidateQueries({ queryKey: ['customers'] })
      setShowMergeSearch(false)
      setMergeQuery('')
    },
  })

  const unmergeMutation = useMutation({
    mutationFn: (sourceId: number) => apiClient.delete(`/api/customers/${id}/merge/${sourceId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['customer', id] })
      qc.invalidateQueries({ queryKey: ['customers'] })
    },
  })

  const { data: mergeSearchResults = [] } = useQuery({
    queryKey: ['customers-search', mergeQuery],
    queryFn: () => apiClient.get('/api/customers', { params: { q: mergeQuery } }).then(r => r.data),
    enabled: mergeQuery.length >= 1,
  })

  const updateAI = async () => {
    if (!note.trim()) return
    setAiLoading(true)
    try {
      await apiClient.post('/api/ai/customer-profile', { customer_id: Number(id), new_note: note })
      qc.invalidateQueries({ queryKey: ['customer', id] })
    } finally { setAiLoading(false) }
  }

  if (isLoading) return <div className="text-gray-400 p-8">読み込み中...</div>
  if (!customer) return <div className="text-gray-400 p-8">顧客が見つかりません</div>

  const prefs = customer.preferences || {}
  // arrival_source: dict {source: count} or legacy list
  const arrivalSourceRaw = prefs.arrival_source || {}
  const arrivalSourceMap: Record<string, number> = Array.isArray(arrivalSourceRaw)
    ? Object.fromEntries((arrivalSourceRaw as string[]).map(s => [s, 1]))
    : arrivalSourceRaw
  const dayPrefs: Record<string, number> = prefs.day_prefs || {}
  const assignedCasts: string[] = prefs.assigned_casts || []

  const daysSinceLastVisit = customer.last_visit_date
    ? Math.floor((new Date().getTime() - new Date(customer.last_visit_date).getTime()) / (1000 * 60 * 60 * 24))
    : null

  const formatInTime = (t: number) => {
    const h = Math.floor(t / 100)
    const m = t % 100
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
  }

  return (
    <div className="space-y-4 max-w-2xl">
      {/* ヘッダー */}
      <div className="flex items-center justify-between gap-3">
        <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-gray-400 hover:text-white text-sm">
          <ArrowLeft className="w-4 h-4" />戻る
        </button>
        <div className="flex gap-2">
          <button onClick={() => setShowEdit(true)} className="btn-secondary flex items-center gap-2 text-sm py-2">
            <Edit2 className="w-4 h-4" />編集
          </button>
          <button onClick={() => setShowDeleteConfirm(true)} className="btn-danger flex items-center gap-2 text-sm py-2">
            <Trash2 className="w-4 h-4" />削除
          </button>
        </div>
      </div>

      {/* 顧客基本情報カード */}
      <div className="card space-y-3">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-3">
            <button
              onClick={() => photoRef.current?.click()}
              className="relative group w-14 h-14 rounded-full overflow-hidden flex-shrink-0 bg-gray-800 flex items-center justify-center"
              title="画像をアップロード"
            >
              {customer.photo_url
                ? <img src={customer.photo_url} alt={customer.name} className="w-full h-full object-cover" />
                : <User className="w-7 h-7 text-gray-500" />
              }
              <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Camera className="w-5 h-5 text-white" />
              </div>
            </button>
            <input
              ref={photoRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) uploadPhoto(f) }}
            />
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-bold text-white">{customer.name}</h1>
                <button
                  onClick={() => setShowMergeSearch(v => !v)}
                  className="flex items-center gap-1 text-xs bg-night-700 hover:bg-night-600 text-gray-400 hover:text-white px-2 py-1 rounded-lg transition-colors"
                  title="顧客名を追加してマージ"
                >
                  <Link className="w-3 h-3" />追加
                </button>
              </div>
              {customer.alias && <p className="text-gray-400 text-sm">({customer.alias})</p>}
              {/* マージ済み顧客名 */}
              {(customer.merged_names || []).length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {(customer.merged_names || []).map((name: string, i: number) => {
                    // merged_customer_idsからsource_idを特定するため顧客リストを検索
                    const sourceId = (customer.merged_customer_ids || [])[i]
                    return (
                      <span key={i} className="flex items-center gap-1 text-xs bg-primary-900/30 text-primary-300 border border-primary-800/40 px-2 py-0.5 rounded-full">
                        {name}
                        <button
                          onClick={() => {
                            if (sourceId && window.confirm(`「${name}」のマージを解除しますか？`)) {
                              unmergeMutation.mutate(sourceId)
                            }
                          }}
                          className="hover:text-red-400 transition-colors ml-0.5"
                          title="マージ解除"
                        >
                          <Unlink className="w-3 h-3" />
                        </button>
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
          <div className="flex gap-2 flex-wrap justify-end">
            {customer.is_blacklisted && (
              <span className="badge bg-red-900/40 text-red-400">ブラックリスト</span>
            )}
            {customer.birthday && isBirthdaySoon(customer.birthday) && (
              <span className="badge bg-yellow-900/40 text-yellow-400">🎂 もうすぐ誕生日</span>
            )}
          </div>
        </div>

        {/* マージ検索パネル */}
        {showMergeSearch && (
          <div className="border border-primary-800/40 bg-night-800 rounded-xl p-3 space-y-2">
            <div className="flex items-center gap-2 text-xs text-primary-400 font-medium">
              <Search className="w-3 h-3" />マージする顧客名を検索
            </div>
            <input
              type="text"
              value={mergeQuery}
              onChange={e => setMergeQuery(e.target.value)}
              placeholder="顧客名を入力..."
              className="input-field w-full text-sm"
              autoFocus
            />
            {mergeSearchResults.length > 0 && (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {mergeSearchResults
                  .filter((c: any) => c.id !== Number(id) && !c.merged_into_id)
                  .map((c: any) => (
                    <button
                      key={c.id}
                      onClick={() => {
                        if (window.confirm(`「${c.name}」を「${customer.name}」にマージしますか？\n※マージ後は再集計されます`)) {
                          mergeMutation.mutate(c.id)
                        }
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg bg-night-700 hover:bg-night-600 transition-colors"
                    >
                      <span className="text-white text-sm">{c.name}</span>
                      {c.alias && <span className="text-gray-500 text-xs ml-2">({c.alias})</span>}
                      <span className="text-gray-500 text-xs ml-2">来店{c.total_visits}回</span>
                    </button>
                  ))}
              </div>
            )}
            {mergeQuery.length >= 1 && mergeSearchResults.filter((c: any) => c.id !== Number(id)).length === 0 && (
              <p className="text-gray-500 text-xs">顧客が見つかりません</p>
            )}
            <button onClick={() => { setShowMergeSearch(false); setMergeQuery('') }} className="text-xs text-gray-500 hover:text-white">閉じる</button>
          </div>
        )}

        {/* KPI グリッド */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <KpiCard label="合計来店数" value={`${customer.total_visits}回`} />
          <KpiCard label="累計会計金額" value={`¥${(customer.total_spend || 0).toLocaleString()}`} highlight />
          <KpiCard label="平均会計額" value={`¥${(prefs.avg_spend || 0).toLocaleString()}`} />
          <KpiCard label="月間平均来店" value={prefs.monthly_avg_visits ? `${prefs.monthly_avg_visits}回` : '-'} />
        </div>

        {/* 来店詳細 */}
        <div className="grid grid-cols-3 gap-2 text-sm">
          <div className="bg-gray-800 rounded-xl p-3 text-center">
            <p className="text-gray-500 text-xs">平均延長</p>
            <p className="text-white font-medium">{prefs.avg_extensions != null ? `${Number(prefs.avg_extensions).toFixed(1)}回` : '-'}</p>
          </div>
          <div className="bg-gray-800 rounded-xl p-3 text-center">
            <p className="text-gray-500 text-xs">平均来店時間</p>
            <p className="text-white font-medium">{prefs.avg_in_time ? formatInTime(prefs.avg_in_time) : '-'}</p>
          </div>
          <div className="bg-gray-800 rounded-xl p-3 text-center">
            <p className="text-gray-500 text-xs">平均人数</p>
            <p className="text-white font-medium">{prefs.avg_group_size != null ? `${Number(prefs.avg_group_size).toFixed(1)}人` : '-'}</p>
          </div>
        </div>
      </div>

      {/* タブ */}
      <div className="flex gap-2 border-b border-gray-700 pb-0">
        {(['info', 'notes', 'history'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === tab ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab === 'info' ? '詳細情報' : tab === 'notes' ? `メモ(${notes.length})` : '来店履歴'}
          </button>
        ))}
      </div>

      {/* タブコンテンツ */}
      {activeTab === 'info' && (
        <div className="space-y-3">
          {/* 基本情報 */}
          <div className="card space-y-3">
            <h3 className="font-medium text-white text-sm">基本情報</h3>
            {customer.customer_code && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">顧客ID</span>
                <span className="text-xs font-mono bg-night-700 text-primary-400 px-2 py-0.5 rounded">{customer.customer_code}</span>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2 text-sm">
              <InfoRow label="電話番号" value={customer.phone_masked || '—'} />
              <InfoRow label="誕生日" value={customer.birthday || '—'} />
              <InfoRow label="初回来店" value={customer.first_visit_date || '—'} />
              <InfoRow label="最終来店" value={customer.last_visit_date
                ? `${customer.last_visit_date}（${daysSinceLastVisit}日経過）`
                : '—'} />
              {customer.age_group && <InfoRow label="年齢層" value={customer.age_group} />}
              {prefs.anniversary_date && <InfoRow label="記念日" value={prefs.anniversary_date} />}
            </div>
            {customer.features && (
              <div>
                <p className="text-xs text-gray-500 mb-1">特徴</p>
                <p className="text-gray-300 text-sm whitespace-pre-wrap">{customer.features}</p>
              </div>
            )}
          </div>

          {/* セット種別 */}
          {(prefs.set_l || prefs.set_mg || prefs.set_shot) && (
            <div className="card space-y-2">
              <h3 className="font-medium text-white text-sm">セット傾向</h3>
              <div className="flex gap-3 text-sm">
                <span className="bg-gray-800 px-3 py-1 rounded-full text-gray-300">L: {prefs.set_l?.toFixed(1) || 0}</span>
                <span className="bg-gray-800 px-3 py-1 rounded-full text-gray-300">MG: {prefs.set_mg?.toFixed(1) || 0}</span>
                <span className="bg-gray-800 px-3 py-1 rounded-full text-gray-300">SHOT: {prefs.set_shot?.toFixed(1) || 0}</span>
              </div>
            </div>
          )}

          {/* 曜日傾向 */}
          {Object.keys(dayPrefs).length > 0 && (
            <div className="card space-y-2">
              <h3 className="font-medium text-white text-sm">来店曜日</h3>
              <div className="flex gap-2 flex-wrap">
                {Object.entries(dayPrefs).sort((a, b) => b[1] - a[1]).map(([day, count]) => (
                  <span key={day} className="bg-pink-900/30 text-pink-300 px-3 py-1 rounded-full text-sm">
                    {day}曜日 ({count}回)
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 来店動機別件数 */}
          {Object.keys(arrivalSourceMap).length > 0 && (
            <div className="card space-y-2">
              <h3 className="font-medium text-white text-sm">来店動機別回数</h3>
              <div className="flex gap-2 flex-wrap">
                {Object.entries(arrivalSourceMap).sort((a, b) => b[1] - a[1]).map(([src, cnt]) => (
                  <span key={src} className="bg-gray-800 text-gray-300 px-3 py-1 rounded-full text-sm">
                    {src} <span className="text-pink-400 font-medium">{cnt}回</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 担当キャスト */}
          {assignedCasts.length > 0 && (
            <div className="card space-y-2">
              <h3 className="font-medium text-white text-sm">担当キャスト</h3>
              <div className="flex gap-2 flex-wrap">
                {assignedCasts.map(cast => (
                  <span key={cast} className="bg-gray-800 text-gray-300 px-3 py-1 rounded-full text-sm">⭐ {cast}</span>
                ))}
              </div>
            </div>
          )}

          {/* NGメモ */}
          {prefs.ng_notes && (
            <div className="card space-y-2 border-red-900/40">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <h3 className="font-medium text-red-400 text-sm">NG・注意事項</h3>
              </div>
              <p className="text-sm text-gray-300">{prefs.ng_notes}</p>
            </div>
          )}

          {/* AIカルテ */}
          <div className="card space-y-3">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-pink-400" />
              <h3 className="font-medium text-white text-sm">AIカルテ</h3>
            </div>
            {customer.ai_summary ? (
              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{customer.ai_summary}</p>
            ) : (
              <p className="text-sm text-gray-500">メモを追加してAIカルテを生成してください</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'notes' && (
        <div className="space-y-4">
          {/* メモ入力 */}
          <div className="card space-y-3">
            <h3 className="font-medium text-white text-sm">接客メモを追加</h3>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              className="input-field w-full h-24 resize-none"
              placeholder="今日の接客メモ、好み、話題など..."
            />
            <div className="flex gap-3">
              <button onClick={() => addNote.mutate()} disabled={!note.trim()} className="btn-secondary flex-1 text-sm">
                メモ保存
              </button>
              <button onClick={updateAI} disabled={!note.trim() || aiLoading} className="btn-primary flex-1 flex items-center justify-center gap-2 text-sm">
                <Bot className="w-4 h-4" />
                {aiLoading ? 'AI更新中...' : 'AIカルテ更新'}
              </button>
            </div>
          </div>

          {/* メモ履歴 */}
          <div className="space-y-2">
            {notes.map((n: any) => (
              <div key={n.id} className="card text-sm space-y-1 relative">
                <button
                  onClick={() => deleteNote.mutate(n.id)}
                  className="absolute top-3 right-3 text-gray-600 hover:text-red-400"
                >
                  <X className="w-4 h-4" />
                </button>
                <p className="text-gray-300 pr-6">{n.note}</p>
                <p className="text-gray-600 text-xs">{new Date(n.created_at).toLocaleString('ja-JP')}</p>
              </div>
            ))}
            {notes.length === 0 && <p className="text-gray-500 text-sm text-center py-8">メモはまだありません</p>}
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <VisitHistoryTab customerId={Number(id)} formatInTime={formatInTime} />
      )}

      {/* 編集モーダル */}
      {showEdit && (
        <EditCustomerModal
          customer={customer}
          onClose={() => setShowEdit(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['customer', id] }); setShowEdit(false) }}
        />
      )}

      {/* 削除確認 */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="card w-full max-w-sm space-y-4">
            <h3 className="font-bold text-white">顧客を削除しますか？</h3>
            <p className="text-sm text-gray-400">「{customer.name}」を削除します。この操作は取り消せません。</p>
            <div className="flex gap-3">
              <button onClick={() => setShowDeleteConfirm(false)} className="btn-secondary flex-1">キャンセル</button>
              <button onClick={() => deleteMutation.mutate()} className="btn-danger flex-1">削除する</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function isBirthdaySoon(birthday: string): boolean {
  const today = new Date()
  const bday = new Date(birthday)
  const thisYear = new Date(today.getFullYear(), bday.getMonth(), bday.getDate())
  const diff = (thisYear.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)
  return diff >= 0 && diff <= 14
}

function KpiCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-gray-800 rounded-xl p-3 text-center">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`font-bold mt-0.5 ${highlight ? 'text-pink-400' : 'text-white'}`}>{value}</p>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-gray-300">{value}</p>
    </div>
  )
}

function EditCustomerModal({ customer, onClose, onSaved }: {
  customer: any; onClose: () => void; onSaved: () => void
}) {
  const [form, setForm] = useState({
    name: customer.name || '',
    alias: customer.alias || '',
    phone: '',
    birthday: customer.birthday || '',
    age_group: customer.age_group || '',
    features: customer.features || '',
    is_blacklisted: customer.is_blacklisted || false,
    preferences: {
      anniversary_date: customer.preferences?.anniversary_date || '',
      ng_notes: customer.preferences?.ng_notes || '',
      assigned_casts: (customer.preferences?.assigned_casts || []).join('、'),
    },
  })

  const mutation = useMutation({
    mutationFn: () => apiClient.put(`/api/customers/${customer.id}`, {
      name: form.name,
      alias: form.alias || null,
      phone: form.phone || null,
      birthday: form.birthday || null,
      age_group: form.age_group || null,
      features: form.features || null,
      is_blacklisted: form.is_blacklisted,
      preferences: {
        ...customer.preferences,
        anniversary_date: form.preferences.anniversary_date || null,
        ng_notes: form.preferences.ng_notes || null,
        assigned_casts: form.preferences.assigned_casts
          ? form.preferences.assigned_casts.split(/[、,，\s]+/).filter(Boolean)
          : [],
      },
    }),
    onSuccess: onSaved,
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 sticky top-0 bg-gray-900">
          <h3 className="font-bold text-white">顧客情報を編集</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="p-4 space-y-3">
          <Field label="名前 *">
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" />
          </Field>
          <Field label="ニックネーム">
            <input value={form.alias} onChange={e => setForm({ ...form, alias: e.target.value })} className="input-field w-full" placeholder="やまちゃん" />
          </Field>
          <Field label="年齢">
            <select value={form.age_group} onChange={e => setForm({ ...form, age_group: e.target.value })} className="input-field w-full">
              <option value="">未設定</option>
              {['20代', '30代', '40代', '50代', '60代', '70代', '80代', '90代'].map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </Field>
          <Field label="特徴">
            <textarea value={form.features} onChange={e => setForm({ ...form, features: e.target.value })} className="input-field w-full h-20 resize-none" placeholder="外見・性格・好みなど" />
          </Field>
          <Field label="電話番号（更新する場合）">
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className="input-field w-full" placeholder="090-0000-0000" />
          </Field>
          <Field label="誕生日">
            <input type="date" value={form.birthday} onChange={e => setForm({ ...form, birthday: e.target.value })} className="input-field w-full" />
          </Field>
          <Field label="記念日（来店記念日など）">
            <input type="date" value={form.preferences.anniversary_date} onChange={e => setForm({ ...form, preferences: { ...form.preferences, anniversary_date: e.target.value } })} className="input-field w-full" />
          </Field>
          <Field label="担当キャスト（読点区切り）">
            <input value={form.preferences.assigned_casts} onChange={e => setForm({ ...form, preferences: { ...form.preferences, assigned_casts: e.target.value } })} className="input-field w-full" placeholder="さくら、あおい" />
          </Field>
          <Field label="NG・注意事項">
            <textarea value={form.preferences.ng_notes} onChange={e => setForm({ ...form, preferences: { ...form.preferences, ng_notes: e.target.value } })} className="input-field w-full h-20 resize-none" placeholder="アレルギー、NGキャスト、注意点など" />
          </Field>
          <div className="flex items-center gap-3">
            <input type="checkbox" id="bl" checked={form.is_blacklisted} onChange={e => setForm({ ...form, is_blacklisted: e.target.checked })} className="w-4 h-4" />
            <label htmlFor="bl" className="text-sm text-gray-300">ブラックリスト登録</label>
          </div>
        </div>
        <div className="p-4 border-t border-gray-700 flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.name} className="btn-primary flex-1 flex items-center justify-center gap-2">
            <Save className="w-4 h-4" />保存
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-gray-500 block mb-1">{label}</label>
      {children}
    </div>
  )
}

function VisitHistoryTab({ customerId, formatInTime }: { customerId: number; formatInTime: (t: number) => string }) {
  const { data: visits = [], isLoading } = useQuery({
    queryKey: ['customer-visits', customerId],
    queryFn: () => apiClient.get(`/api/customers/${customerId}/visits`).then(r => r.data),
  })

  const [expanded, setExpanded] = useState<number | null>(null)

  if (isLoading) return <div className="text-gray-500 text-sm text-center py-8">読み込み中...</div>
  if (visits.length === 0) return (
    <div className="card text-gray-500 text-sm text-center py-8">
      来店履歴がありません（Excelをインポートすると表示されます）
    </div>
  )

  return (
    <div className="space-y-2">
      {visits.map((v: any) => {
        const isOpen = expanded === v.id
        const rawEntries = Object.entries(v.raw_data || {}).filter(([, val]) => val !== null && val !== '' && val !== 'None')
        return (
          <div key={v.id} className="card space-y-2">
            {/* 行ヘッダー */}
            <button
              onClick={() => setExpanded(isOpen ? null : v.id)}
              className="w-full text-left flex items-center justify-between gap-2"
            >
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-sm">
                <span className="text-white font-medium">{v.date}</span>
                <span className={`badge ${v.is_repeat ? 'bg-blue-900/40 text-blue-400' : 'bg-green-900/40 text-green-400'}`}>
                  {v.is_repeat ? 'リピ' : '新規'}
                </span>
                {v.store_name && <span className="text-gray-400 text-xs">{v.store_name}</span>}
                {v.in_time && <span className="text-gray-400 text-xs">IN {formatInTime(v.in_time)}</span>}
                {v.out_time && <span className="text-gray-400 text-xs">OUT {formatInTime(v.out_time)}</span>}
                {v.total_payment > 0 && <span className="text-pink-400 text-xs">¥{v.total_payment.toLocaleString()}</span>}
              </div>
              <span className="text-gray-500 text-xs flex-shrink-0">{isOpen ? '▲' : '▼'}</span>
            </button>

            {/* 詳細（全列データ） */}
            {isOpen && rawEntries.length > 0 && (
              <div className="border-t border-gray-700 pt-2 grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
                {rawEntries.map(([key, val]) => (
                  <div key={key} className="text-xs">
                    <span className="text-gray-500">{key}: </span>
                    <span className="text-gray-200">{String(val)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
