"""空の cast_attendance を持つ日報スナップショットを削除し、前のバージョンを最新に戻す。

「再生成ボタン」事故の復旧用。
close_session 後の勤怠クリア状態で regenerate を呼ぶと cast_attendance が
空のスナップショットが新バージョンとして保存されてしまう。それを削除する。

DRY RUN がデフォルト。--apply で実行。
"""
import argparse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app import models


def is_broken(payload: dict) -> bool:
    """cast_attendance が空 = 壊れたスナップショット"""
    if not isinstance(payload, dict):
        return False
    cast_att = payload.get("cast_attendance") or []
    return len(cast_att) == 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--store-id", type=int, default=None)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(models.DailyReportSnapshot)
        if args.store_id:
            q = q.filter(models.DailyReportSnapshot.store_id == args.store_id)
        snaps = q.order_by(
            models.DailyReportSnapshot.store_id,
            models.DailyReportSnapshot.business_date,
            models.DailyReportSnapshot.version.desc(),
        ).all()

        print("=" * 60)
        print(f"壊れた日報スナップショット削除 [{'APPLY' if args.apply else 'DRY RUN'}]")
        print("=" * 60)

        deleted = 0
        for s in snaps:
            if is_broken(s.payload):
                # 同じ store/date で前バージョンがあるか確認
                prev = db.query(models.DailyReportSnapshot).filter(
                    models.DailyReportSnapshot.store_id == s.store_id,
                    models.DailyReportSnapshot.business_date == s.business_date,
                    models.DailyReportSnapshot.version < s.version,
                ).order_by(models.DailyReportSnapshot.version.desc()).first()
                prev_info = f"前version: v{prev.version}" if prev else "前version: なし（削除すると日報消失）"
                print(f"\n[broken] id={s.id} store={s.store_id} date={s.business_date} v{s.version}")
                print(f"  {prev_info}")
                if args.apply and prev is not None:
                    db.delete(s)
                    deleted += 1
                elif args.apply and prev is None:
                    print("  → スキップ（前versionなし）")

        if args.apply:
            db.commit()
            print(f"\n[APPLY] {deleted} 件削除")
        else:
            print("\n[DRY RUN] --apply で実行")
    finally:
        db.close()


if __name__ == "__main__":
    main()
