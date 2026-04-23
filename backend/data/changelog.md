# TRUST 作業ログ

## 2026-04-17

### DB操作
- **重複店舗削除**: store_id=8(東中野), 9(新中野), 10(方南町) を削除。いずれも is_active=0 でデータ0件の重複レコード。残存店舗: id=1〜7

### バックアップ
- `backend/data/backups/` に以下のCSVバックアップを作成:
  - casts_backup_20260417.csv (223件)
  - customers_backup_20260417.csv (1,481件)
  - customer_visits_backup_20260417.csv (3,349件)
  - cast_daily_pays_backup_20260417.csv (2,704件)
  - confirmed_shifts_backup_20260417.csv (2,717件)

### 設定
- `.claude/settings.json` に編集保護hookを追加（「編集を許可する」で解除）

## 2026-04-18

### バグ修正
- **顧客取込の店舗選択ハードコーディング修正**: `frontend/src/pages/customers/CustomerList.tsx`
  - 店舗選択が「東中野/新中野/方南町」の3店舗固定だったのを、stores配列から動的生成に変更
  - 久我山など新規追加店舗も選択可能に

### スクリプト追加
- `backend/scripts/backup_daily.py`: 日次バックアップスクリプト作成（日報/キャスト/社員/アルバイト/顧客）

## 2026-04-19

### DB操作
- **usersテーブル: emailカラムをusernameにリネーム**
  - admin@trust.com → admin
  - lalahounanlala@gmail.com → lalahounanlala
- 既存2アカウントのusernameをメールのローカル部分に変換

### 機能変更
- **ログイン方式をメールアドレスからユーザー名に変更**
  - backend: User model, auth.py, users.py のemail→username置換
  - frontend: Login.tsx, authStore.ts, AdminPanel.tsx のemail→username置換
  - init_db.py: 初期adminアカウントのemail→username変更

### スクリプト追加
- `backend/scripts/backup_full.py`: 完全バックアップスクリプト（DB+コード+ログ）
- `backend/scripts/generate_manual.py`: POSSYSマニュアルPDF生成スクリプト
- Windowsタスクスケジューラ「POSSYS_DailyBackup」登録（毎朝7時実行）

### 設定変更
- `.claude/settings.json`: 編集保護hookを削除（データ消失/課金リスク時のみ確認に変更）
- ブラウザタブ名をTRUSTからPOSSYSに変更

## 2026-04-24

### 機能改善
- **従業員勤怠: プルダウン選択 + 重複防止実装**

#### DB操作
- `StaffAttendance` に `staff_member_id` FK カラム追加（後方互換性のため `name` は継続保持）
- init_db.py に migration 追加: `ALTER TABLE staff_attendances ADD COLUMN IF NOT EXISTS staff_member_id INTEGER REFERENCES staff_members(id)`

#### Backend修正 (`backend/app/routers/casts.py`)
- `StaffClockInRequest` に `staff_member_id: Optional[int] = None` を追加
- `staff_clock_in()` エンドポイント修正:
  - `staff_member_id` が指定された場合、StaffMember から name・employee_type を自動取得
  - 重複チェック: 同じ `date`/`store_id`/`staff_member_id` の出勤記録があれば 400 エラー
  - `employee_type` を StaffAttendance に保存（"社員" / "アルバイト"）
- `GET /staff-attendance/today/{store_id}` レスポンスに `staff_member_id`, `employee_type` 追加

#### Frontend修正 (`frontend/src/pages/pos/POS.tsx`)
- 従業員勤怠の出勤フロー: テキスト入力 → プルダウン選択に変更
- State変更:
  - `staffClockInStep`: 'name' → 'select' に変更
  - `staffClockInMemberId: number | null` 追加（store_id に紐付ける）
- `staffMemberList` useQuery 追加: `GET /api/staff?store_id={storeId}` で従業員一覧取得
- select modal:
  - "社員" グループと "アルバイト" グループに分けて表示
  - 既に今日出勤済みの従業員は選択不可（staffRecords で判定）
- Mutation修正: `name` → `staff_member_id` を送信

#### 後方互換性
- 従来のテキスト入力（`name` のみ）も引き続きサポート（`staff_member_id=None`）
