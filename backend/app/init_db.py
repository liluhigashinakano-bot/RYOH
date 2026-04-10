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
        # Ticket: 論理削除
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS deleted_by INTEGER REFERENCES users(id)",
        # Ticket: ドラッグ並び順
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS display_order INTEGER",
        # OrderItem: 延長の期番号
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS period_no INTEGER",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS receipt_name VARCHAR(100)",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS ai_advisor_enabled BOOLEAN DEFAULT true",
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS motivation_cast_ids JSON",
        # Cast: 体入ステータス
        "ALTER TABLE casts ADD COLUMN IF NOT EXISTS taiken_status VARCHAR(20)",
        # Store: 領収書関連
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS postal_code VARCHAR(10)",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(20)",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS receipt_footer TEXT",
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


def _merge_split_extensions():
    """同じ ticket × extension × item_name × unit_price の分裂行を1行にマージ。
    AutoExtender の重複POST等で生まれた残骸を起動時に修復する。"""
    from collections import defaultdict
    db = SessionLocal()
    try:
        rows = db.query(models.OrderItem).filter(
            models.OrderItem.item_type == "extension",
            models.OrderItem.canceled_at.is_(None),
            models.OrderItem.cast_id.is_(None),
        ).order_by(models.OrderItem.ticket_id, models.OrderItem.id).all()
        groups: dict = defaultdict(list)
        for r in rows:
            key = (r.ticket_id, r.item_name or "", r.unit_price or 0)
            groups[key].append(r)
        merged = 0
        for items in groups.values():
            if len(items) <= 1:
                continue
            keeper = items[0]
            total_qty = sum((i.quantity or 0) for i in items)
            keeper.quantity = total_qty
            keeper.amount = (keeper.unit_price or 0) * total_qty
            for i in items[1:]:
                db.delete(i)
            merged += 1
        if merged > 0:
            db.commit()
            print(f"[CLEANUP] 分裂延長行 {merged} グループをマージ")
    except Exception as e:
        print(f"[CLEANUP SKIP] merge_split_extensions: {e}")
        db.rollback()
    finally:
        db.close()


def _normalize_extension_count():
    """extension_count を「期数のみ」に正規化する一回限りのマイグレーション。
    旧仕様: extension_count = 期 × ゲスト数, OrderItem 1個=1人分
    新仕様: extension_count = 期数のみ, OrderItem 1個 = 1期 (quantity=人数)
    """
    db = SessionLocal()
    try:
        tickets = db.query(models.Ticket).filter(
            models.Ticket.deleted_at.is_(None),
        ).all()
        fixed_tickets = 0
        for t in tickets:
            ext_items = [i for i in (t.order_items or [])
                         if i.item_type == "extension" and i.canceled_at is None
                         and not (i.item_name or '').startswith('合流')]
            if not ext_items:
                if t.extension_count and t.extension_count > 0:
                    t.extension_count = 0
                    fixed_tickets += 1
                continue
            total_qty = sum((i.quantity or 0) for i in ext_items)
            guest = max(1, t.guest_count or 1)
            # 期数を total_qty / guest として推定
            expected_period = total_qty // guest if guest > 0 else 0
            changed = False
            if t.extension_count != expected_period:
                t.extension_count = expected_period
                changed = True
            # 各 OrderItem を「1期=1行 quantity=人数」に揃え直す
            need_normalize = (
                len(ext_items) != expected_period
                or any((i.quantity or 0) != guest for i in ext_items)
            )
            if expected_period > 0 and need_normalize:
                # 既存行をすべて削除して再作成
                unit_price = ext_items[0].unit_price or 0
                for i in ext_items:
                    db.delete(i)
                for p in range(1, expected_period + 1):
                    db.add(models.OrderItem(
                        ticket_id=t.id,
                        item_type="extension",
                        unit_price=unit_price,
                        quantity=guest,
                        amount=unit_price * guest,
                        period_no=p,
                    ))
                changed = True
            if changed:
                fixed_tickets += 1
        if fixed_tickets > 0:
            db.commit()
            print(f"[CLEANUP] extension を {fixed_tickets} 伝票で正規化")
    except Exception as e:
        print(f"[CLEANUP SKIP] normalize_extension_count: {e}")
        db.rollback()
    finally:
        db.close()


def _fix_help_shifts_without_cast():
    """cast_id=None のヘルプシフトに Cast レコードを紐付ける"""
    db = SessionLocal()
    try:
        orphans = db.query(models.ConfirmedShift).filter(
            models.ConfirmedShift.cast_id.is_(None),
            models.ConfirmedShift.help_cast_name.isnot(None),
        ).all()
        for s in orphans:
            help_name = f"[ヘルプ]{s.help_cast_name}"
            cast = db.query(models.Cast).filter(
                models.Cast.store_id == s.store_id,
                models.Cast.stage_name == help_name,
            ).first()
            if not cast:
                cast = models.Cast(
                    store_id=s.store_id,
                    stage_name=help_name,
                    real_name=s.help_cast_name,
                    rank="C",
                    hourly_rate=1400,
                    help_hourly_rate=1500,
                    is_active=True,
                    notes=f"ヘルプ体入 from store {s.help_from_store_id}",
                )
                db.add(cast)
                db.flush()
            s.cast_id = cast.id
        if orphans:
            db.commit()
            print(f"[INIT] Fixed {len(orphans)} help shifts → cast records created/linked")
    except Exception as e:
        db.rollback()
        print(f"[INIT] _fix_help_shifts_without_cast error: {e}")
    finally:
        db.close()


def init_db():
    models.Base.metadata.create_all(bind=engine)
    _run_migrations(engine)
    _cleanup_broken_snapshots()
    _merge_split_extensions()
    _normalize_extension_count()
    _fix_help_shifts_without_cast()

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
