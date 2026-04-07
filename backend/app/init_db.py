from .database import engine, SessionLocal
from . import models
from .auth import get_password_hash


def _run_migrations(engine):
    """既存テーブルへの列追加マイグレーション（create_allは既存テーブルに列を追加しないため）"""
    migrations = [
        # IncentiveConfig: incentive_mode / fixed_amount 列追加
        "ALTER TABLE incentive_configs ADD COLUMN IF NOT EXISTS incentive_mode VARCHAR(10) DEFAULT 'percent'",
        "ALTER TABLE incentive_configs ADD COLUMN IF NOT EXISTS fixed_amount INTEGER",
        # MenuItemConfig: has_incentive 列追加
        "ALTER TABLE menu_item_configs ADD COLUMN IF NOT EXISTS has_incentive BOOLEAN DEFAULT false",
        # CustomerVisit: raw_data 列追加
        "ALTER TABLE customer_visits ADD COLUMN IF NOT EXISTS raw_data JSON",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__('sqlalchemy').text(sql))
            except Exception as e:
                print(f"[MIGRATION SKIP] {sql[:60]}... → {e}")
        conn.commit()


def init_db():
    models.Base.metadata.create_all(bind=engine)
    _run_migrations(engine)

    db = SessionLocal()
    try:
        # 3店舗データ挿入
        stores_data = [
            {"name": "東中野", "code": "higashinakano", "set_price": 6800, "extension_price": 2700},
            {"name": "新中野", "code": "shinnakano", "set_price": 8100, "extension_price": 2700},
            {"name": "方南町", "code": "honancho", "set_price": 7300, "extension_price": 2700},
        ]

        for store_data in stores_data:
            existing = db.query(models.Store).filter(
                models.Store.code == store_data["code"]
            ).first()
            if not existing:
                store = models.Store(**store_data)
                db.add(store)

        db.commit()

        # superadminアカウント作成
        existing_admin = db.query(models.User).filter(
            models.User.email == "admin@trust.com"
        ).first()
        if not existing_admin:
            admin = models.User(
                email="admin@trust.com",
                password_hash=get_password_hash("trust1234"),
                name="管理者",
                role=models.UserRole.superadmin,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("Superadmin created: admin@trust.com / trust1234")
        else:
            # パスワードハッシュを再生成（bcryptバージョン互換性のため）
            existing_admin.password_hash = get_password_hash("trust1234")
            db.commit()
            print("Superadmin password rehashed: admin@trust.com / trust1234")

        print("Database initialized successfully")

    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
