"""
既存 tickets の visit_type を n_count/r_count に展開する移行スクリプト。

ルール:
- visit_type='N' → n_count = guest_count, r_count = 0
- visit_type='R' → n_count = 0, r_count = guest_count
- visit_type=NULL/その他 → n_count = 0, r_count = 0（ノータッチ）

冪等: 既に n_count + r_count > 0 のレコードはスキップ。
"""
import argparse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app import models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("--dry-run か --apply を指定")
        sys.exit(1)
    if args.dry_run and args.apply:
        print("両方指定不可")
        sys.exit(1)
    dry_run = args.dry_run

    db = SessionLocal()
    try:
        rows = db.query(models.Ticket).all()
        stats = {"total": 0, "n": 0, "r": 0, "skipped_already_set": 0, "skipped_no_type": 0}
        for t in rows:
            stats["total"] += 1
            # 既に設定済みならスキップ（冪等）
            if (t.n_count or 0) > 0 or (t.r_count or 0) > 0:
                stats["skipped_already_set"] += 1
                continue
            vt = t.visit_type
            gc = t.guest_count or 0
            if vt == "N":
                if not dry_run:
                    t.n_count = gc
                    t.r_count = 0
                stats["n"] += 1
            elif vt == "R":
                if not dry_run:
                    t.n_count = 0
                    t.r_count = gc
                stats["r"] += 1
            else:
                stats["skipped_no_type"] += 1

        print("=" * 60)
        print(f"Tickets N/R 移行 [{'DRY RUN' if dry_run else 'APPLY'}]")
        print("=" * 60)
        print(f"  全伝票:            {stats['total']}")
        print(f"  既設定スキップ:    {stats['skipped_already_set']}")
        print(f"  N伝票更新:         {stats['n']}")
        print(f"  R伝票更新:         {stats['r']}")
        print(f"  visit_type無し:    {stats['skipped_no_type']}")

        if dry_run:
            db.rollback()
            print("\n[DRY RUN] 変更なし")
        else:
            db.commit()
            print("\n[APPLY] 反映完了")
    finally:
        db.close()


if __name__ == "__main__":
    main()
