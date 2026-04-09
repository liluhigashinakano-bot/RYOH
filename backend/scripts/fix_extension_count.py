"""tickets.extension_count を実 order_items から再計算して整合させる
（暴走バグの cleanup 後のリカバリ用）"""
import argparse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app import models


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticket-id", type=int, default=None)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(models.Ticket)
        if args.ticket_id:
            q = q.filter(models.Ticket.id == args.ticket_id)
        else:
            q = q.filter(models.Ticket.is_closed == False)
        tickets = q.all()

        print(f"=" * 60)
        print(f"extension_count 補正 [{'APPLY' if args.apply else 'DRY RUN'}]")
        print(f"=" * 60)

        fixed = 0
        for t in tickets:
            ext_items = [i for i in (t.order_items or [])
                         if i.item_type == "extension" and i.canceled_at is None]
            actual_count = sum((i.quantity or 0) for i in ext_items)
            if actual_count != (t.extension_count or 0):
                print(f"  ticket_id={t.id} table={t.table_no}: {t.extension_count} → {actual_count}")
                if args.apply:
                    t.extension_count = actual_count
                    fixed += 1

        if args.apply:
            db.commit()
            print(f"\n[APPLY] {fixed} 件補正")
        else:
            print("\n[DRY RUN] --apply で実行")
    finally:
        db.close()


if __name__ == "__main__":
    main()
