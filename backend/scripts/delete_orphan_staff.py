"""StaffMember マスタに無い名前の StaffAttendance を削除（手動メンテ用）"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
from backend.app.database import SessionLocal
from backend.app import models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="削除する name")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        records = db.query(models.StaffAttendance).filter(
            models.StaffAttendance.name == args.name
        ).all()
        print(f"対象: name={args.name!r} → {len(records)}件")
        for r in records:
            print(f"  id={r.id} store={r.store_id} date={r.date} start={r.actual_start} end={r.actual_end}")
        if args.apply:
            for r in records:
                db.delete(r)
            db.commit()
            print("削除しました")
        else:
            print("（dry-run・--apply で実行）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
