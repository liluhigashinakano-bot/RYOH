"""A-2 dry-run の気になる点を調査"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collections import Counter
from backend.app.database import SessionLocal
from backend.app import models


def main():
    db = SessionLocal()
    try:
        # ─── インセンティブ「設定無」の中身 ───
        print("=" * 60)
        print("[A] インセンティブ設定無の item_type 内訳")
        print("=" * 60)

        # 全店舗の IncentiveConfig.drink_type を取得
        all_configs = db.query(
            models.IncentiveConfig.store_id,
            models.IncentiveConfig.drink_type,
        ).all()
        configs_per_store = {}
        for sid, dt in all_configs:
            configs_per_store.setdefault(sid, set()).add(dt)

        rows = db.query(models.OrderItem).join(models.Ticket).filter(
            models.OrderItem.canceled_at.is_(None),
            models.OrderItem.cast_id.isnot(None),
        ).all()

        no_config = []
        for item in rows:
            store_id = item.ticket.store_id
            if item.item_type not in configs_per_store.get(store_id, set()):
                no_config.append((store_id, item.item_type, item.item_name, item.id))

        # item_type ごとの集計
        ctr = Counter((s, t) for s, t, _, _ in no_config)
        for (sid, itype), cnt in ctr.most_common():
            sample_names = [n for s, t, n, _ in no_config if s == sid and t == itype][:3]
            print(f"  store_id={sid} item_type={itype!r} 件数={cnt} 例={sample_names}")

        # ─── 各店舗の IncentiveConfig 一覧 ───
        print()
        print("=" * 60)
        print("[B] 各店舗の IncentiveConfig 設定一覧")
        print("=" * 60)
        for sid in sorted(configs_per_store):
            store = db.query(models.Store).filter_by(id=sid).first()
            sname = store.name if store else f"id={sid}"
            print(f"  店舗 {sname}: {sorted(configs_per_store[sid])}")

        # ─── [ヘルプ:みう] レコード ───
        print()
        print("=" * 60)
        print("[C] [ヘルプ:みう] StaffAttendance レコード")
        print("=" * 60)
        records = db.query(models.StaffAttendance).filter(
            models.StaffAttendance.name == "[ヘルプ:みう]"
        ).all()
        for r in records:
            print(f"  id={r.id} store_id={r.store_id} date={r.date} "
                  f"actual_start={r.actual_start} actual_end={r.actual_end}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
