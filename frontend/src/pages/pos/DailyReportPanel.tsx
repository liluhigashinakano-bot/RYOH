import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import apiClient from '../../api/client'

type Props = {
  storeId: number
  date: string  // "YYYY-MM-DD"
  onTicketClick?: (ticketId: number) => void
}

const MOTIVATION_ORDER = ['ティッシュ', 'アメブロ', 'LINE', '紹介', 'Google', '看板', '電話', '未設定']

function fmtYen(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return `¥${n.toLocaleString()}`
}

function fmtNum(n: number | null | undefined, suffix = ''): string {
  if (n === null || n === undefined) return '—'
  return `${n.toLocaleString()}${suffix}`
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  // ISO は JST に変換済み naive
  const d = new Date(iso)
  const h = d.getHours()
  const m = d.getMinutes()
  const display = h < 12 ? h + 24 : h
  return `${display.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

function StatBox({ label, value, accent }: { label: string; value: string; accent?: 'green' | 'pink' | 'blue' }) {
  const color =
    accent === 'green' ? 'text-green-400' :
    accent === 'pink' ? 'text-pink-400' :
    accent === 'blue' ? 'text-blue-400' :
    'text-white'
  return (
    <div className="bg-gray-800 rounded-lg px-3 py-2">
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className={`text-sm font-bold ${color}`}>{value}</div>
    </div>
  )
}

export default function DailyReportPanel({ storeId, date, onTicketClick }: Props) {
  const qc = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['daily-report', storeId, date],
    queryFn: () => apiClient.get('/api/reports/daily/latest', {
      params: { store_id: storeId, date }
    }).then(r => r.data),
    enabled: !!storeId && !!date,
    retry: false,
  })

  const regenerate = useMutation({
    mutationFn: (snapshotId: number) =>
      apiClient.post('/api/reports/daily/regenerate', { snapshot_id: snapshotId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['daily-report', storeId, date] })
    },
  })

  if (isLoading) {
    return <div className="text-gray-500 text-xs text-center py-4">日報スナップショット読み込み中...</div>
  }
  if (isError || !data) {
    return (
      <div className="card">
        <div className="text-xs text-gray-500 text-center py-2">この日の日報スナップショットはまだ生成されていません</div>
      </div>
    )
  }

  const p = data.payload || {}
  const sales = p.sales || {}
  const payroll = p.cast_payroll || {}
  const tickets = p.tickets || []
  const cast_attendance = p.cast_attendance || []
  const staff_attendance = p.staff_attendance || []
  const custom_drink_columns: { label: string; short: string }[] = p.custom_drink_columns || []
  const castNameById: Record<number, string> = {}
  for (const c of cast_attendance) {
    if (typeof c.cast_id === 'number') castNameById[c.cast_id] = c.cast_name
  }

  return (
    <div className="space-y-3">
      {/* バージョン情報 */}
      <div className="flex items-center justify-between text-[10px] text-gray-500">
        <span>日報スナップショット v{data.version}</span>
        <div className="flex items-center gap-2">
          <span>{data.created_at ? new Date(data.created_at).toLocaleString('ja-JP') : ''}</span>
          {data.has_raw_inputs && (
            <button
              onClick={() => {
                if (confirm('日報を再生成しますか？（新バージョンとして保存されます）')) {
                  regenerate.mutate(data.id)
                }
              }}
              disabled={regenerate.isPending}
              className="text-[10px] text-primary-400 hover:text-primary-300 underline disabled:opacity-50"
            >
              {regenerate.isPending ? '再生成中...' : '再生成'}
            </button>
          )}
        </div>
      </div>

      {/* 売上サマリー */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">当日売上サマリー</div>
        <div className="grid grid-cols-3 gap-2">
          <StatBox label="売上合計" value={fmtYen(sales.total_amount)} accent="green" />
          <StatBox label="伝票枚数" value={fmtNum(sales.ticket_count)} />
          <StatBox label="来店人数" value={fmtNum(sales.guest_count)} />
          <StatBox label="N人数" value={fmtNum(sales.n_count)} accent="pink" />
          <StatBox label="R人数" value={fmtNum(sales.r_count)} accent="blue" />
          <StatBox label="延長合計" value={fmtNum(sales.extension_count)} />
          <StatBox label="客単価" value={fmtYen(sales.avg_per_guest)} />
          <StatBox label="N客単価" value={fmtYen(sales.avg_per_n)} accent="pink" />
          <StatBox label="R客単価" value={fmtYen(sales.avg_per_r)} accent="blue" />
        </div>
      </div>

      {/* ドリンク・シャンパン */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">ドリンク・シャンパン</div>
        <div className="grid grid-cols-3 gap-2">
          <StatBox label="Sドリンク" value={fmtNum(sales.drink_s_total)} />
          <StatBox label="Lドリンク" value={fmtNum(sales.drink_l_total)} />
          <StatBox label="MGドリンク" value={fmtNum(sales.drink_mg_total)} />
          <StatBox label="シャンパン本数" value={fmtNum(sales.champagne_count)} />
          <StatBox label="シャンパン売上" value={fmtYen(sales.champagne_amount)} />
          <StatBox label="セット数" value={fmtNum(sales.set_count)} />
          <StatBox label="S/セット" value={sales.drink_s_per_set?.toString() ?? '—'} />
          <StatBox label="L/セット" value={sales.drink_l_per_set?.toString() ?? '—'} />
          <StatBox label="MG/セット" value={sales.drink_mg_per_set?.toString() ?? '—'} />
        </div>
      </div>

      {/* 来店動機 / コース / 時間帯 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="card">
          <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">来店動機</div>
          <div className="space-y-1">
            {MOTIVATION_ORDER.filter(m => sales.motivation?.[m]).map(m => (
              <div key={m} className="flex justify-between text-xs">
                <span className="text-gray-300">{m}</span>
                <span className="text-white">{sales.motivation[m]}名</span>
              </div>
            ))}
            {Object.keys(sales.motivation || {}).filter(m => !MOTIVATION_ORDER.includes(m)).map(m => (
              <div key={m} className="flex justify-between text-xs">
                <span className="text-gray-300">{m}</span>
                <span className="text-white">{sales.motivation[m]}名</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">コース別</div>
          <div className="space-y-1">
            {Object.entries(sales.course_counts || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs">
                <span className="text-gray-300">{k === 'standard' ? 'スタンダード' : k === 'premium' ? 'プレミアム' : k}</span>
                <span className="text-white">{v as number}名</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">時間帯別来店</div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {Object.entries(sales.hourly_arrivals || {})
              .sort(([a], [b]) => parseInt(a) - parseInt(b))
              .map(([h, v]) => (
                <div key={h} className="flex justify-between text-xs">
                  <span className="text-gray-300">{h}:00台</span>
                  <span className="text-white">{v as number}名</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* キャスト人件費 */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">キャスト人件費</div>
        <div className="grid grid-cols-4 gap-2">
          <StatBox label="基本給合計" value={fmtYen(payroll.base_pay_total)} />
          <StatBox label="インセンティブ合計" value={fmtYen(payroll.incentive_total)} />
          <StatBox label="実質人件費" value={fmtYen(payroll.actual_pay_total)} accent="pink" />
          <StatBox label="売上対比" value={payroll.ratio_percent !== null && payroll.ratio_percent !== undefined ? `${payroll.ratio_percent}%` : '—'} />
        </div>
      </div>

      {/* キャスト交代回数 */}
      <div className="card">
        <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">
          キャスト交代回数（合計 {sales.cast_rotation_total ?? 0} 回）
        </div>
        {Object.keys(sales.cast_rotation_per_cast || {}).length > 0 && (
          <div>
            <div className="text-[10px] text-gray-500 mb-1">キャスト別（引き継ぎを受けた回数）</div>
            <div className="grid grid-cols-3 gap-1">
              {Object.entries(sales.cast_rotation_per_cast || {}).map(([cid, n]) => {
                const cast = cast_attendance.find((c: any) => String(c.cast_id) === cid)
                return (
                  <div key={cid} className="flex justify-between text-xs bg-gray-800 rounded px-2 py-0.5">
                    <span className="text-gray-300">{cast?.cast_name || `Cast${cid}`}</span>
                    <span className="text-white">{n as number}回</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* キャスト勤務実績（詳細） */}
      {cast_attendance.length > 0 && (
        <div className="card">
          <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">キャスト勤務実績（詳細）</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500">
                  <th className="text-left py-0.5">キャスト</th>
                  <th className="text-center py-0.5">出勤</th>
                  <th className="text-center py-0.5">退勤</th>
                  <th className="text-right py-0.5">時間</th>
                  <th className="text-right py-0.5">時給</th>
                  <th className="text-right py-0.5">基本給</th>
                  <th className="text-right py-0.5">ｲﾝｾﾝﾃｨﾌﾞ</th>
                  <th className="text-right py-0.5">日払い</th>
                  <th className="text-center py-0.5">S</th>
                  <th className="text-center py-0.5">L</th>
                  <th className="text-center py-0.5">MG</th>
                  <th className="text-center py-0.5">SH</th>
                  {custom_drink_columns.map(col => (
                    <th key={col.short} className="text-center py-0.5">{col.short}</th>
                  ))}
                  <th className="text-center py-0.5">ｼｬﾝﾊﾟﾝ</th>
                  <th className="text-right py-0.5">ｼｬﾝﾊﾟﾝ額</th>
                  <th className="text-center py-0.5">接客中会計</th>
                  <th className="text-center py-0.5">ﾃｨｯｼｭ枚</th>
                  <th className="text-right py-0.5">ﾃｨｯｼｭ時間</th>
                  <th className="text-right py-0.5">待機時間</th>
                  <th className="text-right py-0.5">22-26ﾊﾟﾌｫ</th>
                </tr>
              </thead>
              <tbody>
                {cast_attendance.map((c: any, i: number) => (
                  <tr key={i} className="border-t border-gray-800">
                    <td className="py-1 text-white font-medium">
                      {c.cast_name}
                      {c.is_help && <span className="ml-1 text-[10px] text-blue-300">[ヘルプ{c.help_from_store_name ? `:${c.help_from_store_name}` : ''}]</span>}
                      {c.is_off_shift && <span className="ml-1 text-[10px] text-gray-500">[出勤外]</span>}
                    </td>
                    <td className="py-1 text-center text-gray-300 font-mono">{c.is_absent ? <span className="text-red-400">当欠</span> : fmtTime(c.actual_start)}</td>
                    <td className="py-1 text-center text-gray-300 font-mono">{c.is_absent ? '—' : fmtTime(c.actual_end)}</td>
                    <td className="py-1 text-right text-gray-300">{c.work_hours}h</td>
                    <td className="py-1 text-right text-gray-400">{fmtYen(c.applied_hourly_rate)}</td>
                    <td className="py-1 text-right text-gray-300">{fmtYen(c.base_pay)}</td>
                    <td className="py-1 text-right text-pink-300">{fmtYen(c.incentive_total)}</td>
                    <td className="py-1 text-right text-orange-300">{c.daily_pay > 0 ? fmtYen(c.daily_pay) : '—'}</td>
                    <td className="py-1 text-center text-gray-300">{c.drink_s || '—'}</td>
                    <td className="py-1 text-center text-gray-300">{c.drink_l || '—'}</td>
                    <td className="py-1 text-center text-gray-300">{c.drink_mg || '—'}</td>
                    <td className="py-1 text-center text-gray-300">{c.shot_cast || '—'}</td>
                    {custom_drink_columns.map(col => (
                      <td key={col.short} className="py-1 text-center text-gray-300">
                        {(c.custom_drinks?.[col.short] ?? 0) || '—'}
                      </td>
                    ))}
                    <td className="py-1 text-center text-yellow-400">{c.champagne_count > 0 ? c.champagne_count : '—'}</td>
                    <td className="py-1 text-right text-yellow-400">{c.champagne_amount > 0 ? fmtYen(c.champagne_amount) : '—'}</td>
                    <td className="py-1 text-center text-purple-300">{c.closing_count > 0 ? c.closing_count : '—'}</td>
                    <td className="py-1 text-center text-amber-300">{c.tissue_count > 0 ? c.tissue_count : '—'}</td>
                    <td className="py-1 text-right text-amber-300">{c.tissue_hours > 0 ? `${c.tissue_hours}h` : '—'}</td>
                    <td className="py-1 text-right text-gray-400">{c.idle_hours > 0 ? `${c.idle_hours}h` : '—'}</td>
                    <td className="py-1 text-right text-blue-300">{c.perf_22_26 !== null && c.perf_22_26 !== undefined ? fmtYen(c.perf_22_26) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 社員/アルバイト勤務実績 */}
      {staff_attendance.length > 0 && (
        <div className="card">
          <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">社員/アルバイト勤務実績</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="text-left py-0.5">名前</th>
                <th className="text-left py-0.5">区分</th>
                <th className="text-center py-0.5">出勤</th>
                <th className="text-center py-0.5">退勤</th>
                <th className="text-right py-0.5">時間</th>
                <th className="text-right py-0.5">日払い</th>
              </tr>
            </thead>
            <tbody>
              {staff_attendance.map((s: any, i: number) => (
                <tr key={i} className="border-t border-gray-800">
                  <td className="py-1 text-white">{s.name}</td>
                  <td className="py-1 text-gray-400">{s.employee_type === 'staff' ? '社員' : s.employee_type === 'part_time' ? 'アルバイト' : '—'}</td>
                  <td className="py-1 text-center text-gray-300 font-mono">{s.is_absent ? <span className="text-red-400">当欠</span> : fmtTime(s.actual_start)}</td>
                  <td className="py-1 text-center text-gray-300 font-mono">{s.is_absent ? '—' : fmtTime(s.actual_end)}</td>
                  <td className="py-1 text-right text-gray-300">{s.work_hours}h</td>
                  <td className="py-1 text-right text-orange-300">{s.daily_pay > 0 ? fmtYen(s.daily_pay) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 伝票一覧（簡易） */}
      {tickets.length > 0 && (
        <div className="card">
          <div className="text-xs text-gray-400 font-medium border-b border-gray-700 pb-1 mb-2">伝票一覧（{tickets.length}件）</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500">
                  <th className="text-left py-0.5">卓</th>
                  <th className="text-center py-0.5">入店</th>
                  <th className="text-center py-0.5">退店</th>
                  <th className="text-center py-0.5">名</th>
                  <th className="text-center py-0.5">N/R</th>
                  <th className="text-center py-0.5">コース</th>
                  <th className="text-center py-0.5">延長</th>
                  <th className="text-center py-0.5">交代</th>
                  <th className="text-center py-0.5">S/L/MG/SH</th>
                  {custom_drink_columns.map(col => (
                    <th key={col.short} className="text-center py-0.5">{col.short}</th>
                  ))}
                  <th className="text-center py-0.5">ｼｬﾝﾊﾟﾝ</th>
                  <th className="text-right py-0.5">ｼｬﾝﾊﾟﾝ額</th>
                  <th className="text-left py-0.5">会計担当</th>
                  <th className="text-right py-0.5">金額</th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((t: any) => (
                  <tr key={t.id}
                    className={`border-t border-gray-800 ${onTicketClick ? 'cursor-pointer hover:bg-gray-800/50' : ''}`}
                    onClick={() => onTicketClick?.(t.id)}>
                    <td className="py-1 text-white">{t.table_no || '—'}</td>
                    <td className="py-1 text-center font-mono text-gray-400">{fmtTime(t.started_at)}</td>
                    <td className="py-1 text-center font-mono text-gray-400">{fmtTime(t.ended_at)}</td>
                    <td className="py-1 text-center text-gray-300">{t.guest_count}</td>
                    <td className="py-1 text-center text-gray-300">
                      <span className="text-pink-400">N{t.n_count}</span>/<span className="text-blue-400">R{t.r_count}</span>
                    </td>
                    <td className="py-1 text-center text-gray-300">
                      {t.plan_type === 'standard' ? 'STD' : t.plan_type === 'premium' ? 'PRE' : '—'}
                    </td>
                    <td className="py-1 text-center text-gray-300">{t.extension_count}</td>
                    <td className="py-1 text-center text-gray-300">{t.rotation_count}</td>
                    <td className="py-1 text-center text-gray-400 text-[10px]">
                      {t.drink_s}/{t.drink_l}/{t.drink_mg}/{t.shot_cast}
                    </td>
                    {custom_drink_columns.map(col => (
                      <td key={col.short} className="py-1 text-center text-gray-300">
                        {(t.custom_drinks?.[col.short] ?? 0) || '—'}
                      </td>
                    ))}
                    <td className="py-1 text-center text-yellow-400">{t.champagne_count > 0 ? t.champagne_count : '—'}</td>
                    <td className="py-1 text-right text-yellow-400">{t.champagne_amount > 0 ? fmtYen(t.champagne_amount) : '—'}</td>
                    <td className="py-1 text-purple-300">{t.closing_cast_name || (t.closing_cast_id ? castNameById[t.closing_cast_id] : '') || '—'}</td>
                    <td className="py-1 text-right text-green-400">{fmtYen(t.total_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
