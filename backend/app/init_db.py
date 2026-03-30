from .database import engine, SessionLocal
from . import models
from .auth import get_password_hash


def init_db():
    models.Base.metadata.create_all(bind=engine)

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

        print("Database initialized successfully")

    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
