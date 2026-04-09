import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../../api/client'
import { useAuthStore } from '../../store/authStore'

function fmtYen(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return `¥${n.toLocaleString()}`
}

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString()
}

function StatBox({ label, value, accent }: { label: string; value: string; accent?: 'green' | 'pink' | 'blue' | 'yellow' }) {
  const color =
    accent === 'green' ? 'text-green-400' :
    accent === 'pink' ? 'text-pink-400' :
    accent === 'blue' ? 'text-blue-400' :
    accent === 'yellow' ? 'text-yellow-400' :
    'text-white'
  return (
    <div className="bg-gray-800 rounded-lg px-3 py-2">
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className={`text-base font-bold ${color}`}>{value}</div>
    </div>
  )
}

export default function MonthlyReport() {
  const { stores } = useAuthStore()
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? 0)
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['monthly-report', selectedStoreId, year, month],
    queryFn: () => apiClient.get('/api/reports/monthly', {
      params: { store_id: selectedStoreId, year, month }
    }).then(r => r.data),
    enabled: !!selectedStoreId,
    retry: false,
  })

  const summary = data?.summary || {}
  const breakdown: any[] = data?.daily_breakdown || []
  const castSummary: any[] = summary.cast_summary || []
  const staffSummary: any[] = summary.staff_summary || []

  // キャスト累積に出てくる custom_drinks のキー（略称）を集めて列定義
  const customDrinkShorts = useMemo(() => {
    const set = new Set<string>()
    for (const c of castSummary) {
      for (const k of Object.keys(c.custom_drinks || {})) set.add(k)
    }
    return Array.from(set).sort()
  }, [castSummary])

  // 日別バーの最大値（スケール用）
  const maxAmount = useMemo(
    () => Math.max(1, ...breakdown.map(b => b.total_amount || 0)),
    [breakdown]
  )

  // 年プルダウン: 過去5年〜今年
  const yearOptions = useMemo(() => {
    const ys: number[] = []
    for (let y = today.getFullYear() - 5; y <= today.getFullYear() + 1; y++) ys.push(y)
    return ys
  }, [])

  return (
    <div className="space-y-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white">月次レポート</h1>
        <div className="flex items-center gap-2">
          <select
            value={selectedStoreId}
            onChange={e => setSelectedStoreId(Number(e.target.value))}
            className="input-field text-sm"
          >
            {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select
            value={year}
            onChange={e => setYear(Number(e.target.value))}
            className="input-field text-sm"
          >
            {yearOptions.map(y => <option key={y} value={y}>{y}年</option>)}
          </select>
          <select
            value={month}
            onChange={e => setMonth(Number(e.target.value))}
            className="input-field text-sm"
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
              <option key={m} value={m}>{m}月</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && <div className="text-gray-500 text-sm">読み込み中...</div>}
      {isError && <div className="text-red-400 text-sm">取得に失敗しました</div>}

      {data && (
        <>
          <div className="text-xs text-gray-500">
            集計期間: {data.start} 〜 {data.end} / 集計日数: {data.report_days}日
          </div>

          {/* サマリー */}
          <div className="card">
            <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">月次サマリー</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <StatBox label="売上合計" value={fmtYen(summary.total_amount)} accent="green" />
              <StatBox label="伝票枚数" value={fmtNum(summary.ticket_count)} />
              <StatBox label="来店人数" value={fmtNum(summary.guest_count)} />
              <StatBox label="客単価" value={fmtYen(summary.avg_per_guest)} />
              <StatBox label="N人数" value={fmtNum(summary.n_count)} accent="pink" />
              <StatBox label="R人数" value={fmtNum(summary.r_count)} accent="blue" />
              <StatBox label="N客単価" value={fmtYen(summary.avg_per_n)} accent="pink" />
              <StatBox label="R客単価" value={fmtYen(summary.avg_per_r)} accent="blue" />
              <StatBox label="延長合計" value={fmtNum(summary.extension_count)} />
              <StatBox label="セット数" value={fmtNum(summary.set_count)} />
              <StatBox label="キャスト交代計" value={fmtNum(summary.cast_rotation_total)} />
              <StatBox label="人件費率" value={summary.ratio_percent != null ? `${summary.ratio_percent}%` : '—'} accent="pink" />
            </div>
          </div>

          {/* ドリンク・シャンパン */}
          <div className="card">
            <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">ドリンク・シャンパン</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <StatBox label="Sドリンク" value={fmtNum(summary.drink_s_total)} />
              <StatBox label="Lドリンク" value={fmtNum(summary.drink_l_total)} />
              <StatBox label="MGドリンク" value={fmtNum(summary.drink_mg_total)} />
              <StatBox label="シャンパン本数" value={fmtNum(summary.champagne_count)} accent="yellow" />
              <StatBox label="S/セット" value={summary.drink_s_per_set?.toString() ?? '—'} />
              <StatBox label="L/セット" value={summary.drink_l_per_set?.toString() ?? '—'} />
              <StatBox label="MG/セット" value={summary.drink_mg_per_set?.toString() ?? '—'} />
              <StatBox label="シャンパン売上" value={fmtYen(summary.champagne_amount)} accent="yellow" />
              {(summary.custom_drink_columns || []).map((col: any) => (
                <StatBox
                  key={col.short}
                  label={`${col.label}（${col.short}）`}
                  value={fmtNum((summary.custom_drinks_total || {})[col.short] ?? 0)}
                />
              ))}
            </div>
          </div>

          {/* 人件費 */}
          <div className="card">
            <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">人件費</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <StatBox label="基本給合計" value={fmtYen(summary.base_pay_total)} />
              <StatBox label="インセンティブ合計" value={fmtYen(summary.incentive_total)} accent="pink" />
              <StatBox label="実質人件費合計" value={fmtYen(summary.actual_pay_total)} />
              <StatBox label="売上対比" value={summary.ratio_percent != null ? `${summary.ratio_percent}%` : '—'} accent="pink" />
            </div>
          </div>

          {/* 経費 */}
          <div className="card">
            <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">経費</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <StatBox label="酒類経費" value={fmtYen(summary.alcohol_expense)} />
              <StatBox label="その他経費" value={fmtYen(summary.other_expense)} />
              <StatBox label="経費合計" value={fmtYen((summary.alcohol_expense || 0) + (summary.other_expense || 0))} />
            </div>
          </div>

          {/* 来店動機 / 時間帯 / コース */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="card">
              <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">来店動機</div>
              <table className="w-full text-xs">
                <tbody>
                  {Object.entries(summary.motivation || {}).map(([k, v]) => (
                    <tr key={k} className="border-t border-gray-800">
                      <td className="py-1 text-gray-300">{k}</td>
                      <td className="py-1 text-right text-white">{fmtNum(v as number)}</td>
                    </tr>
                  ))}
                  {Object.keys(summary.motivation || {}).length === 0 && (
                    <tr><td className="text-gray-600 py-2">データなし</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="card">
              <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">時間帯別来店</div>
              <table className="w-full text-xs">
                <tbody>
                  {Object.entries(summary.hourly_arrivals || {}).sort(([a], [b]) => Number(a) - Number(b)).map(([k, v]) => (
                    <tr key={k} className="border-t border-gray-800">
                      <td className="py-1 text-gray-300">{k}時台</td>
                      <td className="py-1 text-right text-white">{fmtNum(v as number)}</td>
                    </tr>
                  ))}
                  {Object.keys(summary.hourly_arrivals || {}).length === 0 && (
                    <tr><td className="text-gray-600 py-2">データなし</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="card">
              <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">コース内訳</div>
              <table className="w-full text-xs">
                <tbody>
                  {Object.entries(summary.course_counts || {}).map(([k, v]) => (
                    <tr key={k} className="border-t border-gray-800">
                      <td className="py-1 text-gray-300">{k === 'standard' ? 'スタンダード' : k === 'premium' ? 'プレミアム' : k}</td>
                      <td className="py-1 text-right text-white">{fmtNum(v as number)}</td>
                    </tr>
                  ))}
                  {Object.keys(summary.course_counts || {}).length === 0 && (
                    <tr><td className="text-gray-600 py-2">データなし</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* キャスト別月次累積 */}
          {castSummary.length > 0 && (
            <div className="card">
              <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">キャスト別月次累積（{castSummary.length}名）</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500">
                      <th className="text-left py-0.5">キャスト</th>
                      <th className="text-right py-0.5">出勤日</th>
                      <th className="text-right py-0.5">時間</th>
                      <th className="text-right py-0.5">基本給</th>
                      <th className="text-right py-0.5">ｲﾝｾﾝﾃｨﾌﾞ</th>
                      <th className="text-right py-0.5">日払い</th>
                      <th className="text-center py-0.5">S</th>
                      <th className="text-center py-0.5">L</th>
                      <th className="text-center py-0.5">MG</th>
                      <th className="text-center py-0.5">SH</th>
                      {customDrinkShorts.map(s => (
                        <th key={s} className="text-center py-0.5">{s}</th>
                      ))}
                      <th className="text-center py-0.5">ｼｬﾝﾊﾟﾝ</th>
                      <th className="text-right py-0.5">ｼｬﾝﾊﾟﾝ額</th>
                      <th className="text-center py-0.5">接客中会計</th>
                      <th className="text-center py-0.5">ﾃｨｯｼｭ枚</th>
                      <th className="text-right py-0.5">ﾃｨｯｼｭ時間</th>
                      <th className="text-right py-0.5">待機時間</th>
                      <th className="text-right py-0.5">22-26ﾊﾟﾌｫ</th>
                      <th className="text-center py-0.5">N/Rﾃｨｯｼｭ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {castSummary.map((c, i) => (
                      <tr key={i} className="border-t border-gray-800">
                        <td className="py-1 text-white font-medium">
                          {c.cast_name}
                          {c.is_help && <span className="ml-1 text-[10px] text-blue-300">[ヘルプ]</span>}
                        </td>
                        <td className="py-1 text-right text-gray-300">{c.work_days}日</td>
                        <td className="py-1 text-right text-gray-300">{c.work_hours_total}h</td>
                        <td className="py-1 text-right text-gray-300">{fmtYen(c.base_pay_total)}</td>
                        <td className="py-1 text-right text-pink-300">{fmtYen(c.incentive_total)}</td>
                        <td className="py-1 text-right text-orange-300">{c.daily_pay_total > 0 ? fmtYen(c.daily_pay_total) : '—'}</td>
                        <td className="py-1 text-center text-gray-300">{c.drink_s || '—'}</td>
                        <td className="py-1 text-center text-gray-300">{c.drink_l || '—'}</td>
                        <td className="py-1 text-center text-gray-300">{c.drink_mg || '—'}</td>
                        <td className="py-1 text-center text-gray-300">{c.shot_cast || '—'}</td>
                        {customDrinkShorts.map(s => (
                          <td key={s} className="py-1 text-center text-gray-300">{(c.custom_drinks?.[s] ?? 0) || '—'}</td>
                        ))}
                        <td className="py-1 text-center text-yellow-400">{c.champagne_count > 0 ? c.champagne_count : '—'}</td>
                        <td className="py-1 text-right text-yellow-400">{c.champagne_amount > 0 ? fmtYen(c.champagne_amount) : '—'}</td>
                        <td className="py-1 text-center text-purple-300">{c.closing_count > 0 ? c.closing_count : '—'}</td>
                        <td className="py-1 text-center text-amber-300">{c.tissue_count > 0 ? c.tissue_count : '—'}</td>
                        <td className="py-1 text-right text-amber-300">{c.tissue_hours > 0 ? `${c.tissue_hours}h` : '—'}</td>
                        <td className="py-1 text-right text-gray-400">{c.idle_hours > 0 ? `${c.idle_hours}h` : '—'}</td>
                        <td className="py-1 text-right text-blue-300">{c.perf_22_26_total > 0 ? fmtYen(c.perf_22_26_total) : '—'}</td>
                        <td className="py-1 text-center text-gray-400">
                          <span className="text-pink-400">{c.n_tissue_count}</span>/<span className="text-blue-400">{c.r_tissue_count}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 社員/アルバイト別月次累積 */}
          {staffSummary.length > 0 && (
            <div className="card">
              <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">社員/アルバイト別月次累積（{staffSummary.length}名）</div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500">
                    <th className="text-left py-0.5">名前</th>
                    <th className="text-left py-0.5">区分</th>
                    <th className="text-right py-0.5">出勤日</th>
                    <th className="text-right py-0.5">時間</th>
                    <th className="text-right py-0.5">日払い合計</th>
                  </tr>
                </thead>
                <tbody>
                  {staffSummary.map((s, i) => (
                    <tr key={i} className="border-t border-gray-800">
                      <td className="py-1 text-white">{s.name}</td>
                      <td className="py-1 text-gray-400">
                        {s.employee_type === 'staff' ? '社員' : s.employee_type === 'part_time' ? 'アルバイト' : '—'}
                      </td>
                      <td className="py-1 text-right text-gray-300">{s.work_days}日</td>
                      <td className="py-1 text-right text-gray-300">{s.work_hours_total}h</td>
                      <td className="py-1 text-right text-orange-300">{s.daily_pay_total > 0 ? fmtYen(s.daily_pay_total) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 日別売上推移 */}
          <div className="card">
            <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-3">日別売上推移（{breakdown.length}日）</div>
            {breakdown.length === 0 ? (
              <div className="text-xs text-gray-600 py-4 text-center">この月の日報スナップショットはまだありません</div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500">
                    <th className="text-left py-0.5">日付</th>
                    <th className="text-right py-0.5">売上</th>
                    <th className="text-right py-0.5">人数</th>
                    <th className="text-left py-0.5 pl-3">推移</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.map(b => {
                    const w = Math.max(1, Math.round((b.total_amount || 0) * 100 / maxAmount))
                    return (
                      <tr key={b.business_date} className="border-t border-gray-800">
                        <td className="py-1 text-gray-300 font-mono">{b.business_date}</td>
                        <td className="py-1 text-right text-green-400">{fmtYen(b.total_amount)}</td>
                        <td className="py-1 text-right text-gray-400">{fmtNum(b.guest_count)}</td>
                        <td className="py-1 pl-3">
                          <div className="bg-green-500/30 h-2 rounded" style={{ width: `${w}%` }} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
