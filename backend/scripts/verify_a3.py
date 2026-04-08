"""A-3 動作確認: 直近の OrderItem の incentive_snapshot を見る"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app import models


def main():
    db = SessionLocal()
    try:
        rows = db.query(models.OrderItem).order_by(models.OrderItem.id.desc()).limit(5).all()
        print("=" * 60)
        print("直近のOrderItem 5件")
        print("=" * 60)
        for r in rows:
            print(f"\nid={r.id} ticket={r.ticket_id}")
            print(f"  item_type={r.item_type} item_name={r.item_name!r}")
            print(f"  cast_id={r.cast_id} qty={r.quantity} unit_price={r.unit_price}")
            print(f"  created_at={r.created_at}")
            print(f"  incentive_snapshot={r.incentive_snapshot}")
            print(f"  cast_distribution={r.cast_distribution}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
