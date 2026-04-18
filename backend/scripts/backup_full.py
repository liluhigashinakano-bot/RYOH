"""毎朝7時実行：DB + コード変更 + 作業ログの完全バックアップ"""
import shutil
import zipfile
import sqlite3
import csv
import os
import subprocess
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_DIR, "backend", "data", "trust.db")
BACKUP_ROOT = r"C:\Users\lalal\OneDrive\Desktop\POSshiftバックアップ"


def run():
    today = datetime.now().strftime("%Y%m%d")
    backup_dir = os.path.join(BACKUP_ROOT, today)
    os.makedirs(backup_dir, exist_ok=True)

    log_lines = [f"[{datetime.now().isoformat()}] Daily backup started"]

    # --- 1. DB backup ---
    db_dest = os.path.join(backup_dir, "trust.db")
    shutil.copy2(DB_PATH, db_dest)
    db_size = os.path.getsize(db_dest) / (1024 * 1024)
    log_lines.append(f"  DB: trust.db ({db_size:.1f}MB)")

    # --- 2. DB tables CSV export ---
    csv_dir = os.path.join(backup_dir, "csv")
    os.makedirs(csv_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        try:
            cur.execute(f'SELECT * FROM "{t}"')
            rows = cur.fetchall()
            if not rows:
                continue
            cols = rows[0].keys()
            fpath = os.path.join(csv_dir, f"{t}.csv")
            with open(fpath, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow(list(r))
            log_lines.append(f"  CSV: {t} ({len(rows)}件)")
        except Exception as e:
            log_lines.append(f"  CSV: {t} ERROR: {e}")
    conn.close()

    # --- 3. Git diff (code changes since last commit) ---
    try:
        os.chdir(PROJECT_DIR)
        # Recent commits log
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-20"],
            capture_output=True, text=True, encoding="utf-8"
        )
        log_path = os.path.join(backup_dir, "git_log.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(git_log.stdout)
        log_lines.append(f"  Git log: 最新20コミット保存")

        # Uncommitted changes
        git_diff = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if git_diff.stdout.strip():
            diff_path = os.path.join(backup_dir, "uncommitted_changes.diff")
            full_diff = subprocess.run(
                ["git", "diff"],
                capture_output=True, text=True, encoding="utf-8"
            )
            with open(diff_path, "w", encoding="utf-8") as f:
                f.write(full_diff.stdout)
            log_lines.append(f"  Uncommitted changes: saved")
        else:
            log_lines.append(f"  Uncommitted changes: none")
    except Exception as e:
        log_lines.append(f"  Git: ERROR {e}")

    # --- 4. Code ZIP (changed files only, or full if first backup) ---
    zip_path = os.path.join(backup_dir, "code_changes.zip")
    exclude_dirs = {"node_modules", "venv", ".git", "__pycache__", ".next", "dist", "cropped"}
    exclude_files = {"trust.db"}
    count = 0
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(PROJECT_DIR):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                for f in files:
                    if f in exclude_files:
                        continue
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, PROJECT_DIR)
                    try:
                        zf.write(full, arcname)
                        count += 1
                    except Exception:
                        pass
        zip_size = os.path.getsize(zip_path) / (1024 * 1024)
        log_lines.append(f"  Code ZIP: {count}files ({zip_size:.1f}MB)")
    except Exception as e:
        log_lines.append(f"  Code ZIP: ERROR {e}")

    # --- 5. Changelog copy ---
    changelog = os.path.join(PROJECT_DIR, "backend", "data", "changelog.md")
    if os.path.exists(changelog):
        shutil.copy2(changelog, os.path.join(backup_dir, "changelog.md"))
        log_lines.append(f"  Changelog: copied")

    # --- 6. Write backup log ---
    log_lines.append(f"[{datetime.now().isoformat()}] Backup completed")
    log_text = "\n".join(log_lines)
    print(log_text)

    # Append to master log
    master_log = os.path.join(BACKUP_ROOT, "backup_history.log")
    with open(master_log, "a", encoding="utf-8") as f:
        f.write("\n" + log_text + "\n")

    # Save daily log
    with open(os.path.join(backup_dir, "backup_log.txt"), "w", encoding="utf-8") as f:
        f.write(log_text)


if __name__ == "__main__":
    run()
