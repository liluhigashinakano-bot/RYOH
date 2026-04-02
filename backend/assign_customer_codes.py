"""既存顧客全員に顧客IDを割り当てる一括スクリプト"""
from app.database import engine
from sqlalchemy.orm import Session
from app import models

with Session(engine) as db:
    customers_without_code = (
        db.query(models.Customer)
        .filter(
            (models.Customer.customer_code == None) | (models.Customer.customer_code == "")
        )
        .order_by(models.Customer.store_id, models.Customer.id)
        .all()
    )

    print(f"未割り当て顧客数: {len(customers_without_code)}")

    # 店舗ごとの現在の最大番号を取得
    store_max = {}
    stores = db.query(models.Store).all()
    for store in stores:
        prefix = store.code
        existing = db.query(models.Customer.customer_code).filter(
            models.Customer.customer_code.like(f"{prefix}C%"),
            models.Customer.customer_code != None,
        ).all()
        max_num = 0
        for (code,) in existing:
            if code:
                try:
                    num = int(code[len(prefix) + 1:])
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        store_max[store.id] = (store.code, max_num)

    for customer in customers_without_code:
        sid = customer.store_id or 1
        store_code, max_num = store_max.get(sid, (None, 0))
        if not store_code:
            print(f"  SKIP: customer_id={customer.id} ({customer.name}) - 店舗情報なし")
            continue
        next_num = max_num + 1
        new_code = f"{store_code}C{next_num:05d}"
        customer.customer_code = new_code
        store_max[sid] = (store_code, next_num)
        print(f"  OK: {customer.name} -> {new_code}")

    db.commit()
    print("\n完了!")

input("Press Enter to close...")
