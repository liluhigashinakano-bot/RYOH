"""既存キャスト全員にキャストIDを割り当てる一括スクリプト"""
from app.database import engine
from sqlalchemy.orm import Session
from app import models

with Session(engine) as db:
    # cast_codeが未設定のキャストを店舗ごとに処理
    casts_without_code = (
        db.query(models.Cast)
        .filter(
            (models.Cast.cast_code == None) | (models.Cast.cast_code == "")
        )
        .order_by(models.Cast.store_id, models.Cast.id)
        .all()
    )

    print(f"未割り当てキャスト数: {len(casts_without_code)}")

    # 店舗ごとの現在の最大番号を先に取得
    store_max = {}
    stores = db.query(models.Store).all()
    for store in stores:
        prefix = store.code
        existing = db.query(models.Cast.cast_code).filter(
            models.Cast.cast_code.like(f"{prefix}F%"),
            models.Cast.cast_code != None,
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

    # 割り当て処理
    for cast in casts_without_code:
        store_code, max_num = store_max.get(cast.store_id, (None, 0))
        if not store_code:
            print(f"  SKIP: cast_id={cast.id} ({cast.stage_name}) - 店舗情報なし")
            continue
        next_num = max_num + 1
        new_code = f"{store_code}F{next_num:04d}"
        cast.cast_code = new_code
        store_max[cast.store_id] = (store_code, next_num)
        print(f"  OK: {cast.stage_name} → {new_code}")

    db.commit()
    print("\n完了！")

input("Press Enter to close...")
