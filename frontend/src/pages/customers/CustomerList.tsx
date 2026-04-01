import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, Plus, X, User, Upload, Cake } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import apiClient from '../../api/client'

type SortKey =
  | '50音' | '来店回数' | '累計会計金額' | '平均会計額'
  | '平均延長' | '平均来店時間' | '月間平均来店'
  | 'L数' | 'MG数' | 'ショット数'
  | '初回来店' | '最終来店'
  | 'ポイント残高'

function sortCustomers(customers: any[], key: SortKey, asc: boolean): any[] {
  const arr = [...customers]
  const dir = asc ? 1 : -1
  const dateVal = (d: string | null) => d ? new Date(d).getTime() : 0
  switch (key) {
    case '50音':
      return arr.sort((a, b) => dir * a.name.localeCompare(b.name, 'ja'))
    case '来店回数':
      return arr.sort((a, b) => dir * ((a.total_visits || 0) - (b.total_visits || 0)))
    case '累計会計金額':
      return arr.sort((a, b) => dir * ((a.total_spend || 0) - (b.total_spend || 0)))
    case '平均会計額':
      return arr.sort((a, b) => dir * ((a.preferences?.avg_spend || 0) - (b.preferences?.avg_spend || 0)))
    case '平均延長':
      return arr.sort((a, b) => dir * ((a.preferences?.avg_extensions || 0) - (b.preferences?.avg_extensions || 0)))
    case '平均来店時間':
      return arr.sort((a, b) => dir * ((a.preferences?.avg_in_time || 9999) - (b.preferences?.avg_in_time || 9999)))
    case '月間平均来店':
      return arr.sort((a, b) => dir * ((a.preferences?.monthly_avg_visits || 0) - (b.preferences?.monthly_avg_visits || 0)))
    case 'L数':
      return arr.sort((a, b) => dir * ((a.preferences?.set_l || 0) - (b.preferences?.set_l || 0)))
    case 'MG数':
      return arr.sort((a, b) => dir * ((a.preferences?.set_mg || 0) - (b.preferences?.set_mg || 0)))
    case 'ショット数':
      return arr.sort((a, b) => dir * ((a.preferences?.set_shot || 0) - (b.preferences?.set_shot || 0)))
    case '初回来店':
      return arr.sort((a, b) => dir * (dateVal(a.first_visit_date) - dateVal(b.first_visit_date)))
    case '最終来店':
      return arr.sort((a, b) => dir * (dateVal(a.last_visit_date) - dateVal(b.last_visit_date)))
    case 'ポイント残高':
      return arr.sort((a, b) => dir * ((a.point_balance || 0) - (b.point_balance || 0)))
    default:
      return arr
  }
}

function formatInTime(t: number): string {
  const h = Math.floor(t / 100)
  const m = t % 100
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

export default function CustomerList() {
  const { stores } = useAuthStore()
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('来店回数')
  const [sortAsc, setSortAsc] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [storeId, setStoreId] = useState<number | null>(null)
  const navigate = useNavigate()

  const { data: rawCustomers = [] } = useQuery({
    queryKey: ['customers', q, storeId],
    queryFn: () => apiClient.get('/api/customers', {
      params: { ...(q ? { q } : {}), ...(storeId ? { store_id: storeId } : {}) }
    }).then(r => r.data),
  })

  const customers = sortCustomers(rawCustomers, sortKey, sortAsc)

  const { data: birthdays = [] } = useQuery({
    queryKey: ['birthdays'],
    queryFn: () => apiClient.get('/api/customers/birthdays/upcoming', { params: { days: 14 } }).then(r => r.data),
    staleTime: 1000 * 60 * 10,
  })

  const sortOptions: SortKey[] = [
    '50音', '来店回数', '累計会計金額', '平均会計額',
    '平均延長', '平均来店時間', '月間平均来店',
    'L数', 'MG数', 'ショット数',
    '初回来店', '最終来店', 'ポイント残高',
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">顧客管理</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowImport(true)} className="btn-secondary flex items-center gap-2 text-sm">
            <Upload className="w-4 h-4" />
            Excel取込
          </button>
          <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            顧客追加
          </button>
        </div>
      </div>

      {/* 店舗タブ */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setStoreId(null)}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
            storeId === null ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400 hover:text-white'
          }`}
        >
          全店舗
        </button>
        {stores.map(s => (
          <button
            key={s.id}
            onClick={() => setStoreId(s.id)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
              storeId === s.id ? 'bg-primary-600 text-white' : 'bg-night-700 text-gray-400 hover:text-white'
            }`}
          >
            {s.name}
          </button>
        ))}
      </div>

      {/* 誕生日アラート */}
      {birthdays.length > 0 && (
        <div className="card border-yellow-800/50 bg-yellow-900/10 space-y-2">
          <div className="flex items-center gap-2">
            <Cake className="w-4 h-4 text-yellow-400" />
            <p className="text-sm font-medium text-yellow-400">今後14日以内に誕生日</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {birthdays.map((b: any) => (
              <button
                key={b.id}
                onClick={() => navigate(`/customers/${b.id}`)}
                className="bg-yellow-900/30 border border-yellow-800/50 text-yellow-300 text-xs px-3 py-1.5 rounded-full hover:bg-yellow-900/50 transition-colors"
              >
                🎂 {b.name}{b.alias ? ` (${b.alias})` : ''} — {b.days_until === 0 ? '今日！' : `あと${b.days_until}日`}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 検索・ソート */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="名前・ニックネームで検索"
            className="input-field w-full pl-9"
          />
        </div>
        <select
          value={sortKey}
          onChange={e => setSortKey(e.target.value as SortKey)}
          className="input-field text-sm pr-8"
        >
          {sortOptions.map(k => <option key={k}>{k}</option>)}
        </select>
        <button
          onClick={() => setSortAsc(v => !v)}
          className="input-field text-sm px-3 flex-shrink-0"
          title={sortAsc ? '昇順' : '降順'}
        >
          {sortAsc ? '↑' : '↓'}
        </button>
      </div>

      {/* 顧客一覧 */}
      <div className="space-y-2">
        {customers.map((c: any) => {
          const prefs = c.preferences || {}
          const dayPrefs: Record<string, number> = prefs.day_prefs || {}
          const allDays = Object.entries(dayPrefs).sort((a, b) => b[1] - a[1])
          return (
            <button
              key={c.id}
              onClick={() => navigate(`/customers/${c.id}`)}
              className="card w-full text-left flex items-start gap-3 hover:border-pink-700/50 transition-colors active:scale-[0.99]"
            >
              <div className="w-7 h-7 rounded-full bg-gray-800 flex items-center justify-center flex-shrink-0 mt-0.5 overflow-hidden">
                {c.photo_url
                  ? <img src={c.photo_url} alt={c.name} className="w-full h-full object-cover" />
                  : <User className="w-3.5 h-3.5 text-gray-500" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-medium text-white">{c.name}</p>
                  {c.alias && <span className="text-gray-400 text-sm">{c.alias}</span>}
                  {c.age_group && <span className="text-gray-500 text-xs">{c.age_group}</span>}
                  {c.features && <span className="text-gray-500 text-xs truncate max-w-[160px]">{c.features}</span>}
                  {c.is_blacklisted && <span className="badge bg-red-900/40 text-red-400 text-xs">BL</span>}
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-xs text-gray-400">
                  <span>来店<span className="text-white ml-0.5">{c.total_visits}回</span></span>
                  <span>累計<span className="text-white ml-0.5">¥{(c.total_spend || 0).toLocaleString()}</span></span>
                  {prefs.avg_spend > 0 && <span>平均<span className="text-white ml-0.5">¥{(prefs.avg_spend || 0).toLocaleString()}</span></span>}
                  {prefs.avg_extensions != null && <span>平均延長<span className="text-white ml-0.5">{Number(prefs.avg_extensions).toFixed(1)}回</span></span>}
                  {prefs.avg_in_time && <span>平均IN<span className="text-white ml-0.5">{formatInTime(prefs.avg_in_time)}</span></span>}
                  {prefs.monthly_avg_visits && <span>月平均<span className="text-white ml-0.5">{prefs.monthly_avg_visits}回</span></span>}
                  {c.last_visit_date && <span>最終来店<span className="text-white ml-0.5">{c.last_visit_date}</span></span>}
                </div>
                {(prefs.set_l != null || prefs.set_mg != null || prefs.set_shot != null) && (
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-xs text-gray-400">
                    {prefs.set_l != null && <span>L<span className="text-pink-300 ml-0.5">{Number(prefs.set_l).toFixed(1)}</span></span>}
                    {prefs.set_mg != null && <span>MG<span className="text-pink-300 ml-0.5">{Number(prefs.set_mg).toFixed(1)}</span></span>}
                    {prefs.set_shot != null && <span>SHOT<span className="text-pink-300 ml-0.5">{Number(prefs.set_shot).toFixed(1)}</span></span>}
                  </div>
                )}
                {allDays.length > 0 && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {allDays.map(([day, cnt]) => (
                      <span key={day} className="text-xs bg-pink-900/20 text-pink-400 px-1.5 py-0.5 rounded">
                        {day}({cnt})
                      </span>
                    ))}
                  </div>
                )}
                {c.ai_summary && (
                  <p className="mt-1 text-xs text-gray-500 line-clamp-2">{c.ai_summary}</p>
                )}
              </div>
              {!c.last_visit_date && <p className="text-xs text-gray-500 flex-shrink-0">未来店</p>}
            </button>
          )
        })}
        {customers.length === 0 && (
          <div className="text-center text-gray-500 py-12">顧客が見つかりません</div>
        )}
      </div>

      {showAdd && <AddCustomerModal onClose={() => setShowAdd(false)} />}
      {showImport && <ImportExcelModal onClose={() => setShowImport(false)} />}
    </div>
  )
}

function AddCustomerModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', alias: '', phone: '', birthday: '' })

  const mutation = useMutation({
    mutationFn: () => apiClient.post('/api/customers', {
      name: form.name,
      alias: form.alias || null,
      phone: form.phone || null,
      birthday: form.birthday || null,
    }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['customers'] }); onClose() },
  })

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-sm space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">顧客追加</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500 block mb-1">名前 *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="input-field w-full" placeholder="山田 太郎" />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">ニックネーム</label>
            <input value={form.alias} onChange={e => setForm({ ...form, alias: e.target.value })} className="input-field w-full" placeholder="やまちゃん" />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">電話番号</label>
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className="input-field w-full" placeholder="090-0000-0000" />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">誕生日</label>
            <input type="date" value={form.birthday} onChange={e => setForm({ ...form, birthday: e.target.value })} className="input-field w-full" />
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
          <button onClick={() => mutation.mutate()} disabled={!form.name} className="btn-primary flex-1">保存</button>
        </div>
      </div>
    </div>
  )
}

function ImportExcelModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const fileRef2 = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<'list' | 'daily'>('daily')
  const [file, setFile] = useState<File | null>(null)
  const [storeName, setStoreName] = useState('東中野')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleImport = async () => {
    if (!file) return
    setLoading(true)
    setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('store_name', storeName)
      const endpoint = mode === 'daily' ? '/api/excel/import-daily-sheets' : '/api/excel/import-customers'
      const res = await apiClient.post(endpoint, fd)
      setResult({ ...res.data, mode })
      qc.invalidateQueries({ queryKey: ['customers'] })
    } catch (e: any) {
      setError(e.response?.data?.detail || 'インポートに失敗しました')
    }
    setLoading(false)
  }

  const activeRef = mode === 'daily' ? fileRef : fileRef2

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-bold text-white">Excelから顧客取込</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400" /></button>
        </div>

        {!result ? (
          <>
            {/* モード選択 */}
            <div className="flex gap-2">
              <button
                onClick={() => { setMode('daily'); setFile(null); setError('') }}
                className={`flex-1 py-2 rounded-xl text-sm font-medium transition-colors ${mode === 'daily' ? 'bg-pink-700 text-white' : 'bg-gray-800 text-gray-400'}`}
              >
                日報ファイル（旧形式）
              </button>
              <button
                onClick={() => { setMode('list'); setFile(null); setError('') }}
                className={`flex-1 py-2 rounded-xl text-sm font-medium transition-colors ${mode === 'list' ? 'bg-pink-700 text-white' : 'bg-gray-800 text-gray-400'}`}
              >
                顧客情報一覧（新形式）
              </button>
            </div>

            <p className="text-sm text-gray-400">
              {mode === 'daily'
                ? <>「東中野PC日報2月2026.xlsx」など<br /><span className="text-pink-400">1日〜31日シート</span>の来店データをすべて抽出します。</>
                : <>「東中野PC日報_test_v4」など<br /><span className="text-pink-400">「顧客情報一覧」シート</span>から集計データを取込みます。</>
              }
            </p>

            <div>
              <label className="text-xs text-gray-500 block mb-1">店舗名</label>
              <select value={storeName} onChange={e => setStoreName(e.target.value)} className="input-field w-full">
                <option>東中野</option>
                <option>新中野</option>
                <option>方南町</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-gray-500 block mb-1">Excelファイル (.xlsx)</label>
              <input ref={fileRef} type="file" accept=".xlsx,.xls" onChange={e => setFile(e.target.files?.[0] || null)} className="hidden" />
              <input ref={fileRef2} type="file" accept=".xlsx,.xls" onChange={e => setFile(e.target.files?.[0] || null)} className="hidden" />
              <button onClick={() => activeRef.current?.click()} className="btn-secondary w-full flex items-center justify-center gap-2">
                <Upload className="w-4 h-4" />
                {file ? file.name : 'ファイルを選択'}
              </button>
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <div className="flex gap-3">
              <button onClick={onClose} className="btn-secondary flex-1">キャンセル</button>
              <button onClick={handleImport} disabled={!file || loading} className="btn-primary flex-1">
                {loading ? '取込中...' : '取込開始'}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="bg-green-900/20 border border-green-800/40 rounded-xl p-4 space-y-2">
              <p className="text-green-400 font-medium">取込完了！</p>
              <div className="text-sm text-gray-300 space-y-1">
                {result.mode === 'daily' ? (
                  <>
                    <p>来店データ: <span className="text-white font-medium">{result.visits_extracted}件</span></p>
                    <p>新規顧客登録: <span className="text-white font-medium">{result.customers_created}名</span></p>
                    <p>顧客情報更新: <span className="text-white font-medium">{result.customers_updated}名</span></p>
                    <p className="text-xs text-gray-500 mt-2">CSV保存先: data/imports/{result.csv_saved}</p>
                  </>
                ) : (
                  <>
                    <p>新規登録: <span className="text-white font-medium">{result.created}件</span></p>
                    <p>更新: <span className="text-white font-medium">{result.updated}件</span></p>
                    <p>スキップ: <span className="text-gray-500">{result.skipped}件</span></p>
                    <p className="text-xs text-gray-500 mt-2">保存先: {result.file_saved}</p>
                  </>
                )}
              </div>
            </div>
            <button onClick={onClose} className="btn-primary w-full">閉じる</button>
          </>
        )}
      </div>
    </div>
  )
}
