# 日報・月報 計算仕様書 v1 (ドラフト)

> このドキュメントは Phase D（日報機能本体）実装の正本。
> 計算式・データソース・端数処理を明確に定義し、テストの根拠とする。
>
> **レビュアー: リョウ**　各セクション末尾の `[要確認]` 印で確認待ちの項目を示す。

---

## 0. 用語定義

| 用語 | 定義 |
|---|---|
| **N** | 新規顧客（Ticket.visit_type = "N"） |
| **R** | リピーター（Ticket.visit_type = "R"） |
| **セット** | バー営業の課金単位。1セット = 40分。最初の入店40分が1セット、延長1回ごとに+1セット |
| **コース** | スタンダード / プレミアム（Ticket.plan_type） |
| **キャスト選択あり** | MenuItemConfig.cast_required = True のメニュー |
| **インセンティブあり** | IncentiveConfig が設定されているメニュー（drink_type 単位） |
| **キャスト紹介人数（交代回数）** | 同一卓内でキャスト選択ありの注文時刻順に並べ、隣接ペアで cast_id が変わった回数 |
| **営業日** | BusinessSession.date（opened_at の JST 日付） |
| **JST** | Asia/Tokyo（UTC+9）。バー時刻は 24時超え表記（例: 26:00 = 翌2:00） |

---

## 1. ソースデータ

### 既存テーブル
- `tickets`: 伝票
- `order_items`: 注文明細（`incentive_snapshot` / `cast_distribution` 含む）
- `casts`: キャスト
- `confirmed_shifts`: キャスト勤怠
- `staff_attendances`: 社員/アルバイト勤怠（`employee_type` 含む）
- `staff_members`: 社員/アルバイトマスタ
- `business_sessions`: 営業セッション
- `menu_item_configs`: メニュー設定
- `incentive_configs`: インセンティブ設定
- `customers`: 顧客

### 新規テーブル（Phase D で作成予定）
- `daily_reports`: 日報JSON保存
  ```
  id, store_id, business_date, version, payload (jsonb), created_at, created_by
  unique(store_id, business_date, version)
  ```

---

## 2. 営業セッションとの関係

### セッション期間内のチケット抽出
```
SELECT * FROM tickets
WHERE store_id = :store_id
  AND is_closed = TRUE
  AND ended_at >= session.opened_at
  AND (session.closed_at IS NULL OR ended_at <= session.closed_at)
```

### キャンセル除外
すべての売上集計で `order_items.canceled_at IS NULL` を必須条件とする。

---

## 3. 当日売上 セクション

各項目の式とサンプル値を示す。すべて整数（円未満切り捨て）。

### 3.1 全伝票の会計金額合計
```
sum(tickets.total_amount)
```
**サンプル**: 伝票A=¥6,655, 伝票B=¥10,285, 伝票C=¥3,500 → **¥20,440**

### 3.2 合計延長回数
```
sum(tickets.extension_count)
```

### 3.3 N合計数 / R合計数
```
N合計数 = sum(tickets.n_count)
R合計数 = sum(tickets.r_count)
```
- `tickets.n_count` / `tickets.r_count` は伝票内のN人数とR人数を個別管理する新カラム
- 制約: `n_count + r_count == guest_count`（後発合流時もこの不変条件を維持）

### 3.4 合計伝票枚数
```
count(tickets.id)
```
（卓の数 = 伝票の数）

### 3.5 合計来店数
```
sum(tickets.guest_count)
```
（合流分も含む。`guest_count` は合流時に加算済み）

### 3.6 客単価 / N客単価 / R客単価
```
客単価   = 全伝票の会計金額合計 / 合計来店数

# N/R混在時は伝票売上を人数比で按分
各伝票 t について:
  t_n_share = t.total_amount × (t.n_count / t.guest_count)  # 円未満切り捨て
  t_r_share = t.total_amount - t_n_share                     # 残差
N売上合計 = sum(t_n_share)
R売上合計 = sum(t_r_share)

N客単価  = N売上合計 / N合計数
R客単価  = R売上合計 / R合計数
```
**端数**: 円未満切り捨て
**ゼロ除算**: 分母が0なら null（画面では「—」表示）
**サンプル**: N=1人, R=2人, ¥30,000伝票 → N按分¥10,000 / R按分¥20,000 → N客単価¥10,000 / R客単価¥10,000

### 3.7 キャスト紹介人数合計（交代回数）
各卓ごとに以下を計算：
```
卓Tの注文をフィルタ:
  item.cast_id IS NOT NULL AND item.canceled_at IS NULL
  AND MenuItemConfig(item.item_type).cast_required = TRUE
時刻順 (created_at ASC, id ASC) に並べる
i=0..N-1 のうち item[i].cast_id != item[i+1].cast_id の数 = 卓Tの交代回数
```
**サンプル**: あむ→あむ→かのん→あむ → 隣接で違うペアは2 → **2回**

**集計粒度（出力する3つ）**:
- **当日合計** (`cast_rotation_total`): 全卓の交代回数の総和
- **卓単位** (`per_ticket`): `{ticket_id: count}` の辞書
- **キャスト単位** (`per_cast`): `{cast_id: 引き継いだ回数}` の辞書
  - 「キャスト単位」は「あむ→かのん」に切り替わった時に **かのん側に+1**（引き継がれた側）
  - 同じキャスト同士の連続（あむ→あむ）はカウントなし

**月間** ではこの3つをそのまま月次累計する。

### 3.8 スタンダード / プレミアム件数
```
スタンダード件数 = sum(tickets.guest_count) WHERE plan_type = 'standard'
プレミアム件数   = sum(tickets.guest_count) WHERE plan_type = 'premium'
```
（件数 = 人数）

### 3.9 来店動機別合計数
```
動機Mの合計 = sum(tickets.guest_count) WHERE visit_motivation = M
```
**動機リスト**: ティッシュ / アメブロ / LINE / 紹介 / Google / 看板 / 電話 / その他

### 3.10 1時間ごと時間帯別来店人数
```
入店時間 = ticket.started_at（UTC → JST変換）
時間枠 = JSTの時 (バー表記: 19, 20, ..., 28=翌4時, 29=翌5時)
枠Hの来店人数 = sum(tickets.guest_count) WHERE H枠に started_at が含まれる
```
**枠定義**: 19:00台, 20:00台, ..., 29:00台

### 3.11 酒類経費合計 / その他経費合計
```
session.expenses_detail から取得
```

> [要確認] expenses_detail の中の構造を Phase D 着手時にフロント実装を読んで確定する。今は「酒類経費」「その他経費」のキー名と数値型がどう入ってるか不明。

---

## 4. 当月売上 セクション

3.1～3.11 と同じ項目を、**月初〜月末（または当日まで）の全営業セッション分**で集計する。

```
SELECT * FROM business_sessions
WHERE store_id = :store_id
  AND date >= :month_start
  AND date <= :month_end_or_today
  AND is_closed = TRUE
```
各日報JSONを読み込んで足し算する（新規にDB集計はしない＝Phase D の保存仕様と一致）。

**月途中の暫定値**:
- 月末まで日報がない日 → スキップ
- 当日分の日報がまだ無い → 暫定として live 集計を加算

---

## 5. 当日キャスト人件費 セクション

### 5.1 キャスト人件費（基本給）
```
キャスト人件費 = sum(各キャストの労働時間 × 適用時給)
```
- 労働時間 = `(actual_end - actual_start)` を時間単位（30分単位切り捨て）
- 当欠（is_absent=True）は0時間

**適用時給の決定ルール**:
```
通常出勤の場合:
  適用時給 = casts.hourly_rate

ヘルプ出勤の場合（ConfirmedShift.help_from_store_id IS NOT NULL）:
  if casts.help_hourly_rate IS NOT NULL:
      適用時給 = casts.help_hourly_rate  # 個別設定優先
  else:
      適用時給 = casts.hourly_rate + 100  # フォールバック: 基本時給 + 100円
```

### 5.2 インセンティブ合計
```
インセンティブ合計 = sum(各キャストの非シャンパンインセンティブ + シャンパン分配額)
```

**非シャンパン**:
```
そのキャストが受けた order_item の incentive_snapshot.calculated_amount を合算
```

**シャンパン**:
```
代表行の incentive_snapshot.calculated_amount を back_pool として
各 cast_distribution エントリに ratio% で按分
```

### 5.3 実質キャスト人件費
```
実質キャスト人件費 = キャスト人件費 + インセンティブ合計
```

### 5.4 キャスト人件費対比 ％
```
比率 = 実質キャスト人件費 / 当日売上 × 100
```
端数: 小数点第1位で四捨五入（例: 32.5%）

---

## 6. 月間キャスト人件費 セクション

5.1〜5.4 を月単位で。日報JSONの累計。

### 追加項目（当日と月間で同じ項目を持つ）
- Sドリンク合計数 / Lドリンク合計数 / MGドリンク合計数
- シャンパン売上数 / シャンパン売上合計金額
- キャスト選択あり×インセンティブありメニューごとの注文数
- 1セットあたり S/L/MG ドリンク数（後述）

### 1セットあたりドリンク数
```
セット数 = 来店人数 + 延長合計数
1セットあたりSドリンク数 = Sドリンク合計数 / セット数
```
**サンプル**: 来店3人、延長合計9 → セット数12、Sドリンク12 → **1.0**

端数: 小数点第2位まで保持（表示は第1位四捨五入想定）

---

## 7. 伝票一覧（日報の伝票明細）

各伝票につき以下を出力：

| 項目 | ソース |
|---|---|
| 伝票番号 | tickets.id |
| 卓番 | tickets.table_no |
| 入店時間 | tickets.started_at（JST/バー表記） |
| 退店時間 | tickets.ended_at（JST/バー表記） |
| N / R | tickets.visit_type |
| 合計延長数 | tickets.extension_count |
| キャスト紹介人数 | 上記3.7 の卓単位値 |
| コース | tickets.plan_type |
| 合計Sドリンク数 | sum(quantity) WHERE item_type='drink_s' AND canceled IS NULL |
| 合計Lドリンク数 | 同上 drink_l |
| 合計MGドリンク数 | 同上 drink_mg |
| 合計キャストショット数 | 同上 shot_cast |
| シャンパンオーダー内容 | 各シャンパングループの item_name + cast_distribution の構造化情報 |
| キャスト分配内容 | cast_distribution（cast_id → 名前 + ratio）|
| その他キャスト選択ありメニュー注文数 | item_type='custom_menu' のメニュー別 |
| お客様人数 | tickets.guest_count |
| 会計金額 | tickets.total_amount |
| 決済種別 | cash_amount / card_amount / code_amount |
| 顧客名 | customers.name (customer_id 経由) |
| 来店動機 | tickets.visit_motivation |

---

## 8. キャスト勤務実績（日報の勤怠明細）

各シフトレコードにつき以下を出力：

| 項目 | ソース |
|---|---|
| キャスト名 | casts.stage_name または help_cast_name |
| 種別 | 通常出勤 / ヘルプ出勤 |
| ヘルプ所属店舗 | help_from_store_id → store name |
| 出勤時間 | actual_start（JST/バー表記） |
| 退勤時間 | actual_end |
| 遅刻 | is_late |
| 当欠 | is_absent |
| 労働時間 | end - start（30分単位切り捨て） |
| 日払い金額 | 営業締めの「日払い」出金エントリにこのキャスト名があれば、`労働時間 × 1000` |
| キャストショット杯数 | order_items: shot_cast かつ cast_id=このキャスト の sum(quantity) |
| Sドリンク杯数 | 同上 drink_s |
| Lドリンク杯数 | 同上 drink_l |
| MGドリンク杯数 | 同上 drink_mg |
| シャンパン分配合計金額 | cast_distribution からこのキャストの分配額を合計 |
| インセンティブ合計金額 | 5.2 のキャスト単位値 |
| Nティッシュ件数 | tickets WHERE visit_type='N' AND visit_motivation='ティッシュ' AND motivation_cast_id=このキャスト の卓数 |
| Rティッシュ件数 | 同上 visit_type='R' |
| 1時間あたりパフォーマンス | インセンティブ合計 ÷ 労働時間 |
| 22-26時パフォーマンス | (22-26時帯のキャスト選択あり×インセンティブあり注文金額の合計) ÷ (22-26時帯の勤務時間) |
| 担当顧客名一覧 | キャスト選択あり×インセンティブあり注文を受けた卓の顧客名（重複除外） |

### 22-26時パフォーマンスの分母計算
```
勤務時間と (22:00, 26:00) の重なり時間
例: 19:00出勤・27:00退勤 → 22-26 の4時間
例: 23:00出勤・25:00退勤 → 2時間
例: 18:00出勤・21:00退勤 → 0時間
```

### 22-26時パフォーマンスの分子計算
```
そのキャストが受けた order_items のうち
  cast_required=TRUE AND has_incentive=TRUE
  AND created_at の JST が 22:00 ≤ h < 26:00
  AND canceled_at IS NULL
の incentive_snapshot.calculated_amount を合算
```

**確定**: ティッシュ件数は `visit_motivation='ティッシュ' AND motivation_cast_id=このキャスト` の卓数。
**確定**: 日払いはキャスト/アルバイト共通で「労働時間×1000」、社員は8000円固定。

---

## 9. 社員/アルバイト勤務実績

各 StaffAttendance につき：

| 項目 | ソース |
|---|---|
| 名前 | staff_attendances.name |
| 区分 | staff_attendances.employee_type （"staff" / "part_time"） |
| 出勤時間 | actual_start |
| 退勤時間 | actual_end |
| 遅刻 | is_late |
| 当欠 | is_absent |
| 労働時間 | end - start（30分単位切り捨て） |
| 日払い金額 | 営業締めの「日払い」エントリにこの名前があれば: 社員=8000固定、アルバイト=労働時間×1000 |

---

## 10. 日報JSON スキーマ

```json
{
  "version": 1,
  "store_id": 1,
  "store_name": "東中野",
  "business_date": "2026-04-09",
  "session_id": 123,
  "generated_at": "2026-04-09T05:30:00Z",
  "generated_by": "user_id_or_null",

  "sales": {
    "total_amount": 552244,
    "extension_count": 23,
    "n_count": 5,
    "r_count": 8,
    "ticket_count": 6,
    "guest_count": 13,
    "avg_per_guest": 42480,
    "avg_per_n": 38000,
    "avg_per_r": 45000,
    "cast_rotation_total": 12,
    "cast_rotation_per_ticket": {"567": 2, "568": 4, "569": 6},
    "cast_rotation_per_cast":   {"5": 4, "8": 5, "12": 3},
    "course_standard": 8,
    "course_premium": 5,
    "motivation": {"看板": 3, "紹介": 5, "ティッシュ": 2, ...},
    "hourly_arrivals": {"19": 2, "20": 4, "21": 3, ...},
    "alcohol_expense": 12000,
    "other_expense": 3500,
    "drink_s_total": 12,
    "drink_l_total": 18,
    "drink_mg_total": 4,
    "champagne_count": 3,
    "champagne_amount": 90000,
    "set_count": 36,
    "drink_s_per_set": 0.33,
    "drink_l_per_set": 0.50,
    "drink_mg_per_set": 0.11
  },

  "cast_payroll": {
    "base_pay_total": 56000,
    "incentive_total": 23400,
    "actual_pay_total": 79400,
    "ratio_percent": 14.4
  },

  "tickets": [
    {"id": 567, "table_no": "A1", ...}
  ],

  "cast_attendance": [
    {"cast_id": 5, "cast_name": "あむ", ...}
  ],

  "staff_attendance": [
    {"name": "おとと", "employee_type": "part_time", ...}
  ]
}
```

---

## 11. テストケース（最低3パターン）

### Case A: 平均的な営業日
- 伝票5枚 / 来店12人 / N3人 R9人
- ドリンク・シャンパン・延長すべて発生
- キャスト4人勤務
- 期待値: 売上総額・人件費比率・キャスト個人インセンティブを手計算で出して固定

### Case B: 当欠を含む営業日
- キャスト1人当欠
- 労働時間0、日払い0、インセンティブ0
- 売上は他のキャストで出る
- 期待値: 当欠キャストが0で他キャストが正常

### Case C: 22-26時帯の境界ケース
- キャスト 19:00出勤・21:30退勤（22-26時帯と重ならない）
- → 22-26時パフォーマンス = null（ゼロ除算回避）
- キャスト 23:00出勤・25:00退勤（完全に内側）
- → 分母2時間
- キャスト 21:00出勤・27:00退勤（外側にまたがる）
- → 分母4時間

---

## 12. リョウ確認待ち項目（まとめ）

1. ✅ **3.3 N/R混在伝票**: 案B採用（DB拡張）→ Phase A 追加マイグレで実装
2. ✅ **3.7 交代回数**: 当日合計＋卓単位＋キャスト単位の3粒度を出す
3. ⏳ **3.11 経費構造**: Phase D 着手時にフロント実装読み込み
4. ✅ **5.1 ヘルプ時給**: 個別 `help_hourly_rate` 優先、無ければ `hourly_rate + 100`
5. ✅ **8 ティッシュ件数**: motivation_cast_id 指定の卓のみカウント
6. ✅ **8 日払い**: キャスト/アルバイト=労働時間×1000、社員=8000固定

---

## 13. 端数処理ルール

| 項目 | ルール |
|---|---|
| インセンティブ計算（金額） | 計算後 int() で円未満切り捨て |
| 労働時間 | 30分単位切り捨て |
| 客単価 | 円未満切り捨て |
| 1セットあたりドリンク数 | 小数第2位まで保持 |
| 比率 % | 小数第1位で四捨五入 |
| 給与計算（日払い） | 円単位（端数なし） |

---

**変更履歴**
- v1 (2026-04-09): 初版ドラフト
- v2 (2026-04-09): リョウ確認反映
  - N/R を tickets.n_count / r_count で持つように変更（案B）
  - 客単価のN/R按分式を確定
  - 交代回数を3粒度（合計/卓/キャスト）で出力
  - ヘルプ時給ルール確定（help_hourly_rate 優先・フォールバック=hourly_rate+100）
  - ティッシュ件数・日払い計算ルール確定
