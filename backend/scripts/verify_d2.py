"""D-2 動作確認: 直近の DailyReportSnapshot を見る"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app import models


def main():
    db = SessionLocal()
    try:
        rows = db.query(models.DailyReportSnapshot).order_by(
            models.DailyReportSnapshot.id.desc()
        ).limit(3).all()
        print(f"最新 {len(rows)} 件:")
        for r in rows:
            print(f"\n=== id={r.id} store={r.store_id} date={r.business_date} v={r.version} ===")
            print(f"created_at={r.created_at}")
            p = r.payload or {}
            sales = p.get("sales", {})
            print(f"  total_amount: {sales.get('total_amount')}")
            print(f"  ticket_count: {sales.get('ticket_count')}")
            print(f"  guest_count:  {sales.get('guest_count')}")
            print(f"  n/r:          {sales.get('n_count')} / {sales.get('r_count')}")
            print(f"  rotation:     {sales.get('cast_rotation_total')}")
            cp = p.get("cast_payroll", {})
            print(f"  base_pay:     {cp.get('base_pay_total')}")
            print(f"  incentive:    {cp.get('incentive_total')}")
            print(f"  ratio_%:      {cp.get('ratio_percent')}")
            print(f"  cast 数:      {len(p.get('cast_attendance', []))}")
            print(f"  staff 数:     {len(p.get('staff_attendance', []))}")
            print(f"  ticket 数:    {len(p.get('tickets', []))}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
