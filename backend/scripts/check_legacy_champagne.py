"""旧形式（cast_distributionが無い）シャンパンが残ってるか確認"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app import models


def main():
    db = SessionLocal()
    try:
        all_champs = db.query(models.OrderItem).filter(
            models.OrderItem.item_type == "champagne",
            models.OrderItem.canceled_at.is_(None),
        ).all()

        with_dist = [r for r in all_champs if r.cast_distribution]
        without_dist = [r for r in all_champs if not r.cast_distribution]

        print(f"全シャンパン行: {len(all_champs)}")
        print(f"  cast_distribution あり: {len(with_dist)}")
        print(f"  cast_distribution なし: {len(without_dist)}")

        if without_dist:
            print("\n旧形式の残骸:")
            for r in without_dist[:10]:
                print(f"  id={r.id} ticket={r.ticket_id} item_name={r.item_name!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
