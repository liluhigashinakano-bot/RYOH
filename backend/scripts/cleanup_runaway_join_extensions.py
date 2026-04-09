"""暴走バグで生成された合流延長を一括キャンセル化"""
import argparse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from collections import defaultdict
from backend.app.database import SessionLocal
from backend.app import models


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticket-id", type=int, default=None, help="特定の伝票のみ対象")
    p.add_argument("--threshold", type=int, default=4, help="この本数以上の合流延長を持つ伝票のみ対象（1伝票 = 1グループ）")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(models.OrderItem).filter(
            models.OrderItem.canceled_at.is_(None),
            models.OrderItem.item_type == "extension",
            models.OrderItem.item_name.like("合流延長%"),
        )
        if args.ticket_id:
            q = q.filter(models.OrderItem.ticket_id == args.ticket_id)
        rows = q.all()

        # ticket_id 別にグループ化
        by_ticket: dict = defaultdict(list)
        for r in rows:
            by_ticket[r.ticket_id].append(r)

        print(f"=" * 60)
        print(f"合流延長 暴走クリーンアップ [{'APPLY' if args.apply else 'DRY RUN'}]")
        print(f"=" * 60)

        total_canceled = 0
        for tid, items in sorted(by_ticket.items()):
            # quantity 合計（quantity が複数の行があるかも）
            total_qty = sum(i.quantity or 0 for i in items)
            if total_qty < args.threshold:
                print(f"\n[skip] ticket_id={tid} 合流延長合計={total_qty}本（閾値 {args.threshold} 未満）")
                continue

            ticket = db.query(models.Ticket).filter(models.Ticket.id == tid).first()
            if not ticket:
                continue
            if ticket.is_closed:
                print(f"\n[skip] ticket_id={tid} 会計済みのためスキップ")
                continue

            cancel_amount = sum(i.amount or 0 for i in items)
            print(f"\n[target] ticket_id={tid}  table={ticket.table_no}")
            print(f"  対象行数: {len(items)}  合計qty: {total_qty}  キャンセル金額: {cancel_amount}")
            print(f"  現 total_amount: {ticket.total_amount}")
            new_total = max(0, (ticket.total_amount or 0) - cancel_amount)
            print(f"  新 total_amount: {new_total}")

            if args.apply:
                for r in items:
                    r.canceled_at = datetime.utcnow()
                ticket.total_amount = new_total
                # extension_count を実カウントに合わせる
                remaining_ext = sum(
                    (i.quantity or 0) for i in (ticket.order_items or [])
                    if i.item_type == "extension" and i.canceled_at is None
                )
                ticket.extension_count = remaining_ext
                total_canceled += len(items)

        if args.apply:
            db.commit()
            print(f"\n[APPLY] {total_canceled} 行をキャンセル化しました")
        else:
            print(f"\n[DRY RUN] 変更なし")
    finally:
        db.close()


if __name__ == "__main__":
    main()
