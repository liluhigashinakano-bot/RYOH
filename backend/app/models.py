from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float,
    ForeignKey, Text, Enum, JSON, Date, Time
)
from sqlalchemy.orm import relationship
import enum
from .database import Base


class UserRole(str, enum.Enum):
    administrator = "administrator"
    superadmin = "superadmin"  # 後方互換性のため残す
    manager = "manager"
    editor = "editor"
    staff = "staff"
    order = "order"
    cast = "cast"
    readonly = "readonly"


class CastRank(str, enum.Enum):
    S = "S"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    C_PLUS = "C+"
    C = "C"
    D = "D"
    E = "E"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    card = "card"
    code = "code"
    mixed = "mixed"


class AssignmentType(str, enum.Enum):
    honshimei = "honshimei"
    jounai = "jounai"
    douhan = "douhan"
    afutaa = "afutaa"
    help = "help"


class ShiftRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class AIAdviceType(str, enum.Enum):
    rotation = "rotation"
    management = "management"
    forecast = "forecast"
    customer = "customer"


# ─────────────────────────────────────────
# 店舗
# ─────────────────────────────────────────
class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    set_price = Column(Integer, default=0)
    extension_price = Column(Integer, default=0)
    open_time = Column(String(5), nullable=True)   # "19:00"
    close_time = Column(String(5), nullable=True)  # "05:00"
    address = Column(String(200))
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="store")
    casts = relationship("Cast", back_populates="store")
    tickets = relationship("Ticket", back_populates="store")
    daily_reports = relationship("DailyReport", back_populates="store")


# ─────────────────────────────────────────
# ユーザー
# ─────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.staff)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    permissions = Column(JSON, nullable=True)  # nullの場合はロール権限を使用
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="users")
    cast_profile = relationship("Cast", back_populates="user", uselist=False)


class RolePermission(Base):
    """ロール別デフォルト権限"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True)
    role = Column(String(50), unique=True, nullable=False)
    permissions = Column(JSON, nullable=False, default=dict)


# ─────────────────────────────────────────
# キャスト
# ─────────────────────────────────────────
class Cast(Base):
    __tablename__ = "casts"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cast_code = Column(String(20), unique=True, nullable=True, index=True)
    stage_name = Column(String(50), nullable=False)
    real_name = Column(String(100))
    rank = Column(String(10), default="C")
    hourly_rate = Column(Integer, default=1400)
    help_hourly_rate = Column(Integer, default=1500)
    alcohol_tolerance = Column(String(10), default="普通")
    main_time_slot = Column(String(20))
    transport_need = Column(Boolean, default=False)
    nearest_station = Column(String(100))
    notes = Column(Text)
    photo_path = Column(String(500))
    birthday = Column(Date, nullable=True)
    employment_start_date = Column(Date, nullable=True)
    last_rate_change_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    is_retired = Column(Boolean, default=False)
    retired_at = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="casts")
    user = relationship("User", back_populates="cast_profile")
    shift_requests = relationship("CastShiftRequest", back_populates="cast")
    confirmed_shifts = relationship("ConfirmedShift", back_populates="cast")
    assignments = relationship("CastAssignment", back_populates="cast")


# ─────────────────────────────────────────
# 顧客
# ─────────────────────────────────────────
class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    customer_code = Column(String(20), unique=True, nullable=True, index=True)
    name = Column(String(100), nullable=False)
    alias = Column(String(100))
    phone = Column(String(20))
    birthday = Column(Date, nullable=True)
    first_visit_date = Column(Date, nullable=True)
    last_visit_date = Column(Date, nullable=True)
    total_visits = Column(Integer, default=0)
    total_spend = Column(Integer, default=0)
    ltv = Column(Integer, default=0)
    point_balance = Column(Integer, default=0)
    ai_summary = Column(Text)
    age_group = Column(String(10))
    features = Column(Text)
    photo_path = Column(String(500))
    preferences = Column(JSON, default={})
    merged_customer_ids = Column(JSON, default=[])
    merged_into_id = Column(Integer, nullable=True)
    is_blacklisted = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tickets = relationship("Ticket", back_populates="customer")
    bottles = relationship("Bottle", back_populates="customer")
    visit_notes = relationship("CustomerVisitNote", back_populates="customer")
    visits = relationship("CustomerVisit", back_populates="customer")


# ─────────────────────────────────────────
# 来店履歴（Excelインポート）
# ─────────────────────────────────────────
class CustomerVisit(Base):
    __tablename__ = "customer_visits"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    store_name = Column(String(100))
    is_repeat = Column(Boolean, default=True)
    in_time = Column(Integer, nullable=True)
    out_time = Column(Integer, nullable=True)
    total_payment = Column(Integer, default=0)
    raw_data = Column(JSON)        # {header: value} B〜AU列のデータ
    imported_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="visits")


# ─────────────────────────────────────────
# ボトルキープ
# ─────────────────────────────────────────
class Bottle(Base):
    __tablename__ = "bottles"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    bottle_name = Column(String(100), nullable=False)
    unique_code = Column(String(50), unique=True)
    purchased_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    remaining_volume = Column(Integer, default=700)
    price = Column(Integer, default=0)
    is_expired = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    customer = relationship("Customer", back_populates="bottles")


# ─────────────────────────────────────────
# 伝票（POS）
# ─────────────────────────────────────────
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    table_no = Column(String(20))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    is_closed = Column(Boolean, default=False)
    set_count = Column(Integer, default=1)
    extension_count = Column(Integer, default=0)
    total_amount = Column(Integer, default=0)
    discount_amount = Column(Integer, default=0)
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    cash_amount = Column(Integer, default=0)
    card_amount = Column(Integer, default=0)
    code_amount = Column(Integer, default=0)
    staff_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text)
    guest_count = Column(Integer, default=1)
    n_count = Column(Integer, default=0)  # 新規(New)人数
    r_count = Column(Integer, default=0)  # リピーター(Repeat)人数
    plan_type = Column(String(20), nullable=True)
    visit_type = Column(String(5), nullable=True)  # 後方互換用に残す（n_count/r_countが正本）
    set_started_at = Column(DateTime, nullable=True)
    set_is_paused = Column(Boolean, default=False)
    set_paused_at = Column(DateTime, nullable=True)
    set_paused_seconds = Column(Integer, default=0)
    drink_clears = Column(JSON, default=dict)  # {"castId_drinkType": cleared_at_iso}
    visit_motivation = Column(String(50), nullable=True)   # ティッシュ/SNS/LINE/紹介/Google/看板/電話
    motivation_cast_id = Column(Integer, ForeignKey("casts.id"), nullable=True)  # ティッシュ・LINE用キャスト
    motivation_note = Column(String(200), nullable=True)   # 紹介用テキスト
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="tickets")
    customer = relationship("Customer", back_populates="tickets")
    order_items = relationship("OrderItem", back_populates="ticket")
    assignments = relationship("CastAssignment", back_populates="ticket")
    visit_notes = relationship("CustomerVisitNote", back_populates="ticket")
    motivation_cast = relationship("Cast", foreign_keys=[motivation_cast_id])


# ─────────────────────────────────────────
# 注文明細
# ─────────────────────────────────────────
class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    item_type = Column(String(50), nullable=False)
    item_name = Column(String(100))
    quantity = Column(Integer, default=1)
    unit_price = Column(Integer, default=0)
    amount = Column(Integer, default=0)
    cast_id = Column(Integer, ForeignKey("casts.id"), nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    canceled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # シャンパン等の複数キャスト分配: [{"cast_id": 5, "ratio": 60}, ...]
    cast_distribution = Column(JSON, nullable=True)
    # 注文時点のインセンティブスナップショット:
    # {"mode": "percent"|"fixed", "rate": int|None, "fixed_amount": int|None, "calculated_amount": int}
    incentive_snapshot = Column(JSON, nullable=True)

    ticket = relationship("Ticket", back_populates="order_items")
    cast = relationship("Cast", foreign_keys=[cast_id])


# ─────────────────────────────────────────
# 注文変更履歴
# ─────────────────────────────────────────
class OrderItemLog(Base):
    __tablename__ = "order_item_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=True)
    action = Column(String(20), nullable=False)   # 'cancel' | 'update_quantity'
    item_type = Column(String(50))
    item_name = Column(String(100))
    old_quantity = Column(Integer, nullable=True)
    new_quantity = Column(Integer, nullable=True)
    old_amount = Column(Integer, nullable=True)
    new_amount = Column(Integer, nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    operator_name = Column(String(50), nullable=True)  # 手動入力の担当者名
    reason = Column(String(200), nullable=True)         # 変更理由
    changed_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket")
    order_item = relationship("OrderItem")
    changed_by_user = relationship("User", foreign_keys=[changed_by])


# ─────────────────────────────────────────
# 付け回し
# ─────────────────────────────────────────
class CastAssignment(Base):
    __tablename__ = "cast_assignments"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    cast_id = Column(Integer, ForeignKey("casts.id"), nullable=False)
    assignment_type = Column(Enum(AssignmentType), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    back_amount = Column(Integer, default=0)

    ticket = relationship("Ticket", back_populates="assignments")
    cast = relationship("Cast", back_populates="assignments")


# ─────────────────────────────────────────
# 接客メモ
# ─────────────────────────────────────────
class CustomerVisitNote(Base):
    __tablename__ = "customer_visit_notes"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    staff_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=False)
    ai_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="visit_notes")
    ticket = relationship("Ticket", back_populates="visit_notes")


# ─────────────────────────────────────────
# シフト申請・確定
# ─────────────────────────────────────────
class CastShiftRequest(Base):
    __tablename__ = "cast_shift_requests"

    id = Column(Integer, primary_key=True, index=True)
    cast_id = Column(Integer, ForeignKey("casts.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    desired_date = Column(Date, nullable=False)
    desired_start = Column(String(10))
    desired_end = Column(String(10))
    status = Column(Enum(ShiftRequestStatus), default=ShiftRequestStatus.pending)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    cast = relationship("Cast", back_populates="shift_requests")


class ConfirmedShift(Base):
    __tablename__ = "confirmed_shifts"

    id = Column(Integer, primary_key=True, index=True)
    cast_id = Column(Integer, ForeignKey("casts.id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    date = Column(Date, nullable=False)
    planned_start = Column(String(10))
    planned_end = Column(String(10))
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    is_late = Column(Boolean, default=False)
    is_absent = Column(Boolean, default=False)
    help_from_store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    help_cast_name = Column(String(100), nullable=True)
    notes = Column(Text)
    shift_data = Column(JSON)   # Excelインポート分の実績（set_l, mg, drink_back等）

    cast = relationship("Cast", back_populates="confirmed_shifts")
    daily_pay = relationship("CastDailyPay", back_populates="shift", uselist=False)


class CastDailyPay(Base):
    __tablename__ = "cast_daily_pays"

    id = Column(Integer, primary_key=True, index=True)
    shift_id = Column(Integer, ForeignKey("confirmed_shifts.id"), nullable=False)
    base_pay = Column(Integer, default=0)
    drink_back = Column(Integer, default=0)
    champagne_back = Column(Integer, default=0)
    honshimei_back = Column(Integer, default=0)
    douhan_back = Column(Integer, default=0)
    transport_deduction = Column(Integer, default=0)
    tax_deduction = Column(Integer, default=0)
    total_pay = Column(Integer, default=0)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    shift = relationship("ConfirmedShift", back_populates="daily_pay")


# ─────────────────────────────────────────
# 従業員マスタ（社員/アルバイト）
# ─────────────────────────────────────────
class StaffMember(Base):
    __tablename__ = "staff_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    employee_type = Column(String(20), nullable=False)  # "staff" | "part_time"
    position = Column(String(50), nullable=True)        # 社員のみ
    hourly_rate = Column(Integer, nullable=True)        # アルバイトのみ
    store_ids = Column(JSON, default=[])                # 所属店舗IDリスト
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 社員/アルバイト勤怠
# ─────────────────────────────────────────
class StaffAttendance(Base):
    __tablename__ = "staff_attendances"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    date = Column(Date, nullable=False)
    name = Column(String(100), nullable=False)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    is_late = Column(Boolean, default=False)
    is_absent = Column(Boolean, default=False)
    employee_type = Column(String(20), nullable=True)  # "社員" | "アルバイト"
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 日報
# ─────────────────────────────────────────
class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    date = Column(Date, nullable=False)
    new_customers = Column(Integer, default=0)
    repeat_customers = Column(Integer, default=0)
    total_sales = Column(Integer, default=0)
    target_sales = Column(Integer, default=0)
    champagne_count = Column(Integer, default=0)
    champagne_sales = Column(Integer, default=0)
    extension_count = Column(Integer, default=0)
    visit_sources = Column(JSON, default={})
    ai_analysis = Column(Text)
    is_closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="daily_reports")


# ─────────────────────────────────────────
# 日報スナップショット（バージョン管理付き・JSON保存）
# ─────────────────────────────────────────
class DailyReportSnapshot(Base):
    __tablename__ = "daily_report_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    business_date = Column(Date, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 営業セッション
# ─────────────────────────────────────────
class BusinessSession(Base):
    __tablename__ = "business_sessions"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    date = Column(Date, nullable=False)        # 営業日
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    opening_cash = Column(Integer, default=0)    # 開始レジ金（金種合計）
    opening_cash_detail = Column(JSON, nullable=True)  # {10000:枚数, 5000:枚数, ...}
    closing_cash = Column(Integer, nullable=True)       # 終了レジ金
    closing_cash_detail = Column(JSON, nullable=True)
    prev_day_diff = Column(Integer, default=0)   # 前日過不足金
    sales_snapshot = Column(Integer, nullable=True)  # 終了時売上スナップショット
    operator_name = Column(String(50), nullable=True)  # 担当者名
    event_name = Column(String(100), nullable=True)    # 本日企画名
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    is_closed = Column(Boolean, default=False)
    cash_diff = Column(Integer, nullable=True)   # 営業終了時の過不足金（翌日繰越用）
    expenses_detail = Column(JSON, nullable=True)  # 経費・出金明細
    cash_sales = Column(Integer, nullable=True)    # 現金売上合計
    card_sales = Column(Integer, nullable=True)    # カード売上合計
    code_sales = Column(Integer, nullable=True)    # コード売上合計
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store")
    opened_by_user = relationship("User", foreign_keys=[opened_by])
    closed_by_user = relationship("User", foreign_keys=[closed_by])


# ─────────────────────────────────────────
# メニュー設定（追加注文）
# ─────────────────────────────────────────
class MenuItemConfig(Base):
    __tablename__ = "menu_item_configs"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    label = Column(String(100), nullable=False)          # 表示名（例: Lドリンク）
    price = Column(Integer, default=0)                   # 単価
    cast_required = Column(Boolean, default=True)        # キャスト選択が必要か
    has_incentive = Column(Boolean, default=False)       # インセンティブあり/なし
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# インセンティブ設定（日報キャストドリンクバック率）
# ─────────────────────────────────────────
class IncentiveConfig(Base):
    __tablename__ = "incentive_configs"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    drink_type = Column(String(50), nullable=False)      # drink_l / drink_mg / drink_s / shot_cast / champagne / menu_{id}
    incentive_mode = Column(String(10), default="percent")  # 'percent' | 'fixed'
    rate = Column(Integer, default=10)                   # インセンティブ率（%）incentive_mode='percent'の時
    fixed_amount = Column(Integer, nullable=True)        # 固定バック額（円）incentive_mode='fixed'の時
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# AIアドバイス
# ─────────────────────────────────────────
class AIAdvice(Base):
    __tablename__ = "ai_advice"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    advice_type = Column(Enum(AIAdviceType), nullable=False)
    context = Column(JSON, default={})
    advice = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
