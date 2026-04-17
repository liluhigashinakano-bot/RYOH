"""毎朝7時に実行：日報/キャスト/社員/アルバイト/顧客のCSVバックアップ"""
import sqlite3
import csv
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trust.db")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "backups")

TABLES = {
    "casts": "SELECT * FROM casts",
    "staff_members": "SELECT * FROM staff_members",
    "customers": "SELECT * FROM customers",
    "customer_visits": "SELECT * FROM customer_visits",
    "cast_daily_pays": "SELECT * FROM cast_daily_pays",
    "confirmed_shifts": "SELECT * FROM confirmed_shifts",
    "staff_attendances": "SELECT * FROM staff_attendances",
}


def backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    results = []

    for name, query in TABLES.items():
        try:
            cur.execute(query)
            rows = cur.fetchall()
            if not rows:
                results.append(f"  {name}: 0件 (skip)")
                continue
            cols = rows[0].keys()
            fname = f"{name}_backup_{today}.csv"
            fpath = os.path.join(BACKUP_DIR, fname)
            with open(fpath, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow(list(r))
            results.append(f"  {name}: {len(rows)}件 -> {fname}")
        except Exception as e:
            results.append(f"  {name}: ERROR {e}")

    conn.close()

    log_path = os.path.join(BACKUP_DIR, "backup.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now().isoformat()}] Backup completed\n")
        for r in results:
            f.write(r + "\n")

    print(f"[{datetime.now().isoformat()}] Backup completed")
    for r in results:
        print(r)


if __name__ == "__main__":
    backup()
