# TRUST - グランドデザイン最終版
> ナイトレジャー業務統合管理システム

## 1. システム概要

### ビジョン
ナイトワーク経営に特化した、AIを核とするオールインワン業務管理プラットフォーム。
リアルタイムPOS・顧客CRM・シフト管理・給与計算・経営分析を統合し、現場の入力負荷を極限まで下げる。

### 対応店舗（初期）
- 東中野Lilu
- 新中野
- 方南町
※ 店舗の追加・削除はUI上で管理者が随時操作可能

---

## 2. ロール定義とRBAC（権限マトリックス）

| ロール | 説明 | POS入力 | 顧客閲覧 | 顧客編集 | 売上閲覧 | 給与閲覧 | 管理機能 |
|--------|------|---------|---------|---------|---------|---------|---------|
| superadmin | システム全体管理者 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| manager（管理者） | 店舗責任者 | ✅ | ✅ | ✅ | ✅ | ✅（自店） | 一部 |
| editor（編集者） | 現場リーダー | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| staff（従業員） | 社員・スタッフ | ✅ | ✅ | ❌ | 自店のみ | ❌ | ❌ |
| order（オーダー端末） | タブレット注文専用 | ✅（注文のみ） | ❌ | ❌ | ❌ | ❌ | ❌ |
| cast（キャスト） | キャスト本人 | ❌ | 自分の成績のみ | ❌ | ❌ | 自分のみ | ❌ |
| readonly（閲覧用） | 投資家・外部向け | ❌ | ❌ | ❌ | ✅（限定） | ❌ | ❌ |

---

## 3. DBスキーマ設計

### 3-1. コアテーブル

```
stores（店舗）
├── id, name, code, set_price, address, phone
├── created_at, is_active

users（ユーザー）
├── id, email, password_hash, name
├── role: Enum[superadmin, manager, editor, staff, order, cast, readonly]
├── store_id（所属店舗、superadminはNULL）
├── is_active, last_login_at

casts（キャスト）
├── id, store_id, stage_name, real_name
├── rank: Enum[S,A,B+,B,C+,C,D,E]
├── hourly_rate, help_hourly_rate
├── alcohol_tolerance, main_time_slot
├── transport_need, nearest_station
├── notes, is_active
├── user_id（キャストアカウントと紐付け）

customers（顧客）
├── id, name, alias（ニックネーム）, phone, birthday
├── first_visit_date, last_visit_date
├── total_visits, total_spend, ltv
├── point_balance
├── ai_summary（AI自動生成カルテ）
├── preferences（JSON: 好み・特記事項）
├── is_blacklisted

bottles（ボトルキープ）
├── id, customer_id, store_id
├── bottle_name, unique_code
├── purchased_at, expires_at
├── remaining_volume（ml）
├── is_expired
```

### 3-2. POSテーブル

```
tickets（伝票）
├── id, store_id, table_no
├── customer_id（紐付け顧客）
├── started_at, ended_at, is_closed
├── set_count, extension_count
├── total_amount, discount_amount
├── payment_method: Enum[cash, card, mixed]
├── cash_amount, card_amount
├── staff_id（担当社員）
├── notes

order_items（注文明細）
├── id, ticket_id
├── item_type: Enum[set, extension, drink_s, drink_l, drink_mg, shot_cast, shot_guest, champagne, bottle, other]
├── quantity, unit_price, amount
├── cast_id（提供キャスト）
├── canceled_at, canceled_by

cast_assignments（付け回し）
├── id, ticket_id, cast_id
├── type: Enum[honshimei, jounai, douhan, afutaa, help]
├── started_at, ended_at
├── back_amount（バック金額）
```

### 3-3. シフト・給与テーブル

```
cast_shift_requests（シフト申請）
├── id, cast_id, store_id
├── desired_date, desired_start, desired_end
├── status: Enum[pending, approved, rejected]

confirmed_shifts（確定シフト）
├── id, cast_id, store_id, date
├── planned_start, planned_end
├── actual_start, actual_end（打刻）
├── is_late, is_absent
├── help_from_store_id（ヘルプ元）

cast_daily_pay（日払い計算）
├── id, confirmed_shift_id
├── base_pay, drink_back, champagne_back
├── honshimei_back, douhan_back
├── transport_deduction, tax_deduction
├── total_pay（端数切り捨て）

staff_shifts（社員シフト）
├── id, user_id, store_id, date
├── shift_type: Enum[early, mid, late, outro]
├── start_time, end_time
├── is_holiday, holiday_type
├── happy_bonus, daily_pay
├── tissue_count（ティッシュ外出回数）
```

### 3-4. 分析・AIテーブル

```
daily_reports（日報）
├── id, store_id, date
├── new_customers, repeat_customers
├── total_sales, target_sales
├── champagne_count, champagne_sales
├── extension_count
├── visit_sources（JSON: ティッシュ/SNS/Google等）
├── ai_analysis（AI生成経営コメント）
├── is_closed

customer_visit_notes（接客メモ）
├── id, customer_id, ticket_id, staff_id
├── note（自由記述）
├── ai_summary（AI要約）
├── created_at

external_data（外部環境データ）
├── id, store_id, date
├── weather（JSON）
├── local_events（JSON）
├── competitor_data（JSON）
├── fetched_at

ai_advice（AIアドバイス履歴）
├── id, store_id, advice_type: Enum[rotation, management, forecast]
├── context（JSON）, advice（テキスト）
├── created_at
```

---

## 4. リレーション図

```
stores ─┬─ users
        ├─ casts ──── cast_shift_requests
        │           ── confirmed_shifts ── cast_daily_pay
        │           ── cast_assignments
        ├─ tickets ─┬─ order_items
        │           ├─ cast_assignments
        │           └─ customer_visit_notes
        ├─ customers ─┬─ bottles
        │             └─ customer_visit_notes
        ├─ daily_reports
        └─ external_data
```

---

## 5. APIエンドポイント一覧

### Auth
- POST /api/auth/login
- POST /api/auth/refresh
- POST /api/auth/logout

### 店舗管理
- GET/POST /api/stores
- PUT/DELETE /api/stores/{id}

### POS（リアルタイム）
- GET/POST /api/tickets
- PUT /api/tickets/{id}/close
- POST /api/tickets/{id}/orders
- DELETE /api/orders/{id}
- GET /api/tickets/live（WebSocket: リアルタイム売上）

### 顧客
- GET/POST /api/customers
- GET/PUT /api/customers/{id}
- GET /api/customers/search?q=
- POST /api/customers/{id}/notes
- GET /api/customers/{id}/ai-profile

### キャスト
- GET/POST /api/casts
- GET/PUT /api/casts/{id}
- GET /api/casts/{id}/performance

### シフト
- GET/POST /api/shift-requests
- GET /api/shifts/confirmed
- POST /api/shifts/confirm
- POST /api/shifts/timeclock

### 給与
- GET /api/payroll/calculate/{shift_id}
- GET /api/payroll/monthly

### 日報・分析
- GET/POST /api/daily-reports
- GET /api/analytics/summary
- GET /api/analytics/trends

### AI
- POST /api/ai/rotation-advice（付け回しアドバイス）
- POST /api/ai/customer-profile（顧客カルテ更新）
- POST /api/ai/management-advice（経営アドバイス）
- GET /api/ai/forecast（売上予測）

---

## 6. フロントエンド構成

### ページ一覧
```
/ ────────────── ダッシュボード（リアルタイム売上・出勤状況）
/pos ──────────── POSメイン（伝票入力・付け回しAI）
/customers ────── 顧客一覧・検索
/customers/:id ── 顧客詳細・カルテ
/casts ─────────── キャスト一覧
/shifts ────────── シフト管理
/shifts/request ── シフト申請（キャスト向け）
/payroll ───────── 給与計算
/reports ───────── 日報・分析
/analytics ─────── 経営分析AI
/admin ─────────── 管理者設定（店舗・ユーザー・権限）
/cast-app ──────── キャスト専用アプリ（シンプルUI）
```

### レスポンシブ対応方針
- **スマホ（〜768px）**: ボトムナビ、シンプルカード表示
- **タブレット（769〜1024px）**: サイドバー折りたたみ、グリッド2列
- **iPad Pro/PC（1025px〜）**: フルサイドバー、グリッド3〜4列
- POSページはタブレット横向きに最適化

---

## 7. 給与計算ロジック（TDD対象）

### キャスト日払い計算式
```
base_pay = hourly_rate × work_hours (端数切り捨て30分単位)
drink_back = (S×単価 + L×単価 + MG×単価 + shot×単価) × back_rate
champagne_back = (glasses × 単価) × back_rate
honshimei_back = 本指名数 × 本指名バック単価
total_gross = base_pay + drink_back + champagne_back + honshimei_back
transport_deduction = (実費 if transport_need else 0)
tax = total_gross × 0.1 (源泉徴収, 条件による)
total_pay = floor(total_gross - transport_deduction - tax, -2) # 百円単位切り捨て
```

### 消費税計算
```
alcohol: 8% (軽減税率)
set_fee, extension: 10%
mixed: 按分計算
```

---

## 8. AI機能設計

### 付け回しAI
- 入力: 顧客プロフィール + 来店歴 + 現在出勤キャスト + 時刻
- 処理: Claude API呼び出し（ナイトワーク特化プロンプト）
- 出力: 推奨キャスト順位 + 理由

### 顧客カルテAI
- トリガー: 接客メモ保存時
- 処理: 過去メモ + 新規メモをまとめてClaude APIで要約
- 出力: 更新された顧客ai_summary

### 経営分析AI
- 入力: 月次データ + 外部環境データ（天気/イベント/競合）
- 処理: Claude API（経営コンサルプロンプト）
- 出力: 今週の営業方針 + 改善提案

---

## 9. セキュリティ方針
- JWT認証（access: 1h, refresh: 7d）
- 顧客個人情報: APIレスポンスでマスキング（電話番号下4桁のみ等）
- 削除操作: 論理削除のみ（物理削除禁止）
- 全操作ログ: audit_logsテーブルに記録
- HTTPS必須（本番環境）
