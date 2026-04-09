"""分裂した延長注文行を1行にマージするスクリプト

同じ ticket_id × extension × 同じ item_name × 同じ unit_price × 未キャンセル の
複数行を、最古の行 (id 最小) に数量加算してまとめる。
他の行は canceled_at をセット (=ログ的に削除フラグ) する代わりに
物理的に削除する（履歴ログには出ない方が分かりやすいため）。

DRY RUN がデフォルト。--apply で実行。
"""
import argparse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collections import defaultdict
from backend.app.database import SessionLocal
from backend.app import models


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticket-id", type=int, default=None)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(models.OrderItem).filter(
            models.OrderItem.item_type == "extension",
            models.OrderItem.canceled_at.is_(None),
            models.OrderItem.cast_id.is_(None),
        )
        if args.ticket_id:
            q = q.filter(models.OrderItem.ticket_id == args.ticket_id)
        rows = q.order_by(models.OrderItem.ticket_id, models.OrderItem.id).all()

        # キーでグループ化
        groups: dict = defaultdict(list)
        for r in rows:
            key = (r.ticket_id, r.item_name or "", r.unit_price or 0)
            groups[key].append(r)

        print("=" * 60)
        print(f"延長注文マージ [{'APPLY' if args.apply else 'DRY RUN'}]")
        print("=" * 60)

        merged_count = 0
        for key, items in groups.items():
            if len(items) <= 1:
                continue
            ticket_id, name, price = key
            total_qty = sum((i.quantity or 0) for i in items)
            keeper = items[0]
            print(f"\n[merge] ticket={ticket_id} name={name or '(無)'} price={price}")
            print(f"  {len(items)}行 → 1行 (qty合計={total_qty}, keep id={keeper.id})")
            for i in items[1:]:
                print(f"    delete id={i.id} qty={i.quantity}")
            if args.apply:
                keeper.quantity = total_qty
                keeper.amount = price * total_qty
                for i in items[1:]:
                    db.delete(i)
                merged_count += 1

        if args.apply:
            db.commit()
            print(f"\n[APPLY] {merged_count} グループをマージ")
        else:
            print("\n[DRY RUN] --apply で実行")
    finally:
        db.close()


if __name__ == "__main__":
    main()
