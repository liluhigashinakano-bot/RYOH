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
