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
        # OrderItem: custom_menu への item_type 修正（旧コードで 'other'+cast_id として保存されていたもの）
        "UPDATE order_items SET item_type='custom_menu' WHERE item_type='other' AND cast_id IS NOT NULL",
        # Cast: 退店フラグ追加
        "ALTER TABLE casts ADD COLUMN IF NOT EXISTS is_retired BOOLEAN DEFAULT false",
        "ALTER TABLE casts ADD COLUMN IF NOT EXISTS retired_at DATE",
        # ConfirmedShift: cast_id をnullable化・ヘルプキャスト名追加
        "ALTER TABLE confirmed_shifts ALTER COLUMN cast_id DROP NOT NULL",
        "ALTER TABLE confirmed_shifts ADD COLUMN IF NOT EXISTS help_cast_name VARCHAR(100)",
        # User: permissions 列追加
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSON",
        # PostgreSQL enum type に administrator 追加（superadmin → administrator 移行用）
        "ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'administrator'",
        # superadmin → administrator 移行（enum追加後に実行）
        "UPDATE users SET role = 'administrator' WHERE role = 'superadmin'",
        # OrderItem: シャンパン分配・インセンティブスナップショット用JSONカラム追加
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS cast_distribution JSON",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS incentive_snapshot JSON",
        # StaffAttendance: 社員/アルバイト区分追加
        "ALTER TABLE staff_attendances ADD COLUMN IF NOT EXISTS employee_type VARCHAR(20)",
        # Ticket: N/R 個別人数カラム追加（visit_type 1個では混在表現できないため）
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS n_count INTEGER DEFAULT 0",
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS r_count INTEGER DEFAULT 0",
        # DailyReportSnapshot: 再生成用の生入力データ
        "ALTER TABLE daily_report_snapshots ADD COLUMN IF NOT EXISTS raw_inputs JSON",
        # キャストのヘルプ時給は常に基本時給+100に整合（ズレてるデータを修正）
        "UPDATE casts SET help_hourly_rate = hourly_rate + 100 WHERE hourly_rate IS NOT NULL AND (help_hourly_rate IS NULL OR help_hourly_rate <> hourly_rate + 100)",
        # Ticket: featured_cast_id (推しキャスト)
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS featured_cast_id INTEGER REFERENCES casts(id)",
    ]
    # 各マイグレーションを個別トランザクションで実行（1つ失敗しても他に影響しない）
    for sql in migrations:
        try:
            with engine.begin() as conn:
                conn.execute(__import__('sqlalchemy').text(sql))
        except Exception as e:
            print(f"[MIGRATION SKIP] {sql[:60]}... → {e}")


ALL_PERMISSIONS = {
    "realtime": {"view": True},
    "pos": {"view": True, "edit": True},
    "customers": {"view": True, "edit": True},
    "employees": {"view": True, "edit": True},
    "accounts": {"view": True, "edit": True},
    "menus": {"view": True, "edit": True},
}

DEFAULT_ROLE_PERMISSIONS = {
    "manager": {
        "realtime": {"view": True},
        "pos": {"view": True, "edit": True},
        "customers": {"view": True, "edit": True},
        "employees": {"view": True, "edit": True},
        "accounts": {"view": True, "edit": True},
        "menus": {"view": True, "edit": True},
    },
    "editor": {
        "realtime": {"view": True},
        "pos": {"view": True, "edit": True},
        "customers": {"view": True, "edit": True},
        "employees": {"view": True, "edit": False},
        "accounts": {"view": False, "edit": False},
        "menus": {"view": True, "edit": False},
    },
    "staff": {
        "realtime": {"view": True},
        "pos": {"view": True, "edit": True},
        "customers": {"view": True, "edit": False},
        "employees": {"view": False, "edit": False},
        "accounts": {"view": False, "edit": False},
        "menus": {"view": False, "edit": False},
    },
    "order": {
        "realtime": {"view": False},
        "pos": {"view": True, "edit": True},
        "customers": {"view": False, "edit": False},
        "employees": {"view": False, "edit": False},
        "accounts": {"view": False, "edit": False},
        "menus": {"view": False, "edit": False},
    },
    "cast": {
        "realtime": {"view": False},
        "pos": {"view": False, "edit": False},
        "customers": {"view": False, "edit": False},
        "employees": {"view": False, "edit": False},
        "accounts": {"view": False, "edit": False},
        "menus": {"view": False, "edit": False},
    },
    "readonly": {
        "realtime": {"view": True},
        "pos": {"view": True, "edit": False},
        "customers": {"view": True, "edit": False},
        "employees": {"view": True, "edit": False},
        "accounts": {"view": False, "edit": False},
        "menus": {"view": True, "edit": False},
    },
}


def _seed_role_permissions(db):
    for role, perms in DEFAULT_ROLE_PERMISSIONS.items():
        existing = db.query(models.RolePermission).filter_by(role=role).first()
        if not existing:
            db.add(models.RolePermission(role=role, permissions=perms))
    db.commit()


def _cleanup_broken_snapshots():
    """cast_attendance が空の壊れた日報スナップショットを削除（前バージョンがある場合のみ）。
    再生成事故の自動復旧。"""
    db = SessionLocal()
    try:
        snaps = db.query(models.DailyReportSnapshot).all()
        deleted = 0
        for s in snaps:
            payload = s.payload if isinstance(s.payload, dict) else {}
            cast_att = payload.get("cast_attendance") or []
            if len(cast_att) == 0:
                prev = db.query(models.DailyReportSnapshot).filter(
                    models.DailyReportSnapshot.store_id == s.store_id,
                    models.DailyReportSnapshot.business_date == s.business_date,
                    models.DailyReportSnapshot.version < s.version,
                ).order_by(models.DailyReportSnapshot.version.desc()).first()
                if prev is not None:
                    print(f"[CLEANUP] 壊れた日報削除: id={s.id} store={s.store_id} date={s.business_date} v{s.version} (前version v{prev.version})")
                    db.delete(s)
                    deleted += 1
        if deleted > 0:
            db.commit()
            print(f"[CLEANUP] 計 {deleted} 件の壊れた日報スナップショットを削除")
    except Exception as e:
        print(f"[CLEANUP SKIP] {e}")
        db.rollback()
    finally:
        db.close()


def init_db():
    models.Base.metadata.create_all(bind=engine)
    _run_migrations(engine)
    _cleanup_broken_snapshots()

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

        # ロール別デフォルト権限のシード
        _seed_role_permissions(db)

        print("Database initialized successfully")

    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
