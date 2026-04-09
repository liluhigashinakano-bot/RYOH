"""
日報ビルダー:
DB の ORM データを report_calc 用の Input dataclass に変換し、
集計結果を JSON dict として組み立てる。

責務:
- DB アクセス（ここに集約）
- ORM → Input 変換（タイムゾーン、incentive_amount 取得など）
- report_calc 関数群の呼び出し
- JSON dict 組み立て
- スナップショット保存

呼び出し側（営業締めフック・手動再生成API）はこのモジュールの
build_daily_report_payload / save_snapshot のみを使う。
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models
from . import report_calc as rc


# ─────────────────────────────────────────
# JST 変換ユーティリティ
# ─────────────────────────────────────────

def _to_jst(dt: Optional[datetime]) -> Optional[datetime]:
    """UTC naive datetime を JST naive datetime に変換"""
    if dt is None:
        return None
    return dt + timedelta(hours=9)


# ─────────────────────────────────────────
# ORM → Input 変換
# ─────────────────────────────────────────

def _menu_label_to_id(menu_configs: List[models.MenuItemConfig]) -> Dict[str, int]:
    """label -> id"""
    return {m.label: m.id for m in menu_configs if m.is_active}


def _menu_label_meta(menu_configs: List[models.MenuItemConfig]) -> Dict[str, dict]:
    """label -> {cast_required, has_incentive}"""
    return {
        m.label: {"cast_required": bool(m.cast_required), "has_incentive": bool(m.has_incentive)}
        for m in menu_configs if m.is_active
    }


_BUILTIN_DRINK_META = {
    "drink_s": {"cast_required": True, "has_incentive": True},
    "drink_l": {"cast_required": True, "has_incentive": True},
    "drink_mg": {"cast_required": True, "has_incentive": True},
    "shot_cast": {"cast_required": True, "has_incentive": True},
    "champagne": {"cast_required": True, "has_incentive": True},
}


def _resolve_meta(item: models.OrderItem, label_meta: Dict[str, dict]) -> dict:
    """OrderItem から (cast_required, has_incentive) を解決"""
    if item.item_type in _BUILTIN_DRINK_META:
        return _BUILTIN_DRINK_META[item.item_type]
    if item.item_type == "custom_menu":
        # item_name の "[キャスト名]" サフィックスを除去してラベル取得
        from .incentive import strip_cast_suffix
        label = strip_cast_suffix(item.item_name or "")
        return label_meta.get(label, {"cast_required": False, "has_incentive": False})
    return {"cast_required": False, "has_incentive": False}


def _to_order_input(item: models.OrderItem, label_meta: Dict[str, dict]) -> rc.OrderInput:
    snap = item.incentive_snapshot or {}
    incentive_amount = int(snap.get("calculated_amount") or 0) if isinstance(snap, dict) else 0
    meta = _resolve_meta(item, label_meta)
    return rc.OrderInput(
        id=item.id,
        item_type=item.item_type,
        item_name=item.item_name,
        quantity=item.quantity or 0,
        unit_price=item.unit_price or 0,
        cast_id=item.cast_id,
        canceled=item.canceled_at is not None,
        created_at_jst=_to_jst(item.created_at) or datetime.min,
        incentive_amount=incentive_amount,
        cast_distribution=item.cast_distribution if isinstance(item.cast_distribution, list) else None,
        cast_required=meta["cast_required"],
        has_incentive=meta["has_incentive"],
    )


def _to_ticket_input(
    ticket: models.Ticket,
    label_meta: Dict[str, dict],
) -> rc.TicketInput:
    customer_name = None
    if ticket.customer_id and ticket.customer:
        customer_name = ticket.customer.name
    payment = ticket.payment_method.value if ticket.payment_method else None
    return rc.TicketInput(
        id=ticket.id,
        table_no=ticket.table_no,
        started_at_jst=_to_jst(ticket.started_at) or datetime.min,
        ended_at_jst=_to_jst(ticket.ended_at),
        guest_count=ticket.guest_count or 0,
        n_count=ticket.n_count or 0,
        r_count=ticket.r_count or 0,
        extension_count=ticket.extension_count or 0,
        plan_type=ticket.plan_type,
        visit_motivation=ticket.visit_motivation,
        motivation_cast_id=ticket.motivation_cast_id,
        customer_name=customer_name,
        total_amount=ticket.total_amount or 0,
        cash_amount=ticket.cash_amount or 0,
        card_amount=ticket.card_amount or 0,
        code_amount=ticket.code_amount or 0,
        payment_method=payment,
        orders=[_to_order_input(o, label_meta) for o in (ticket.order_items or [])],
    )


def _to_shift_input(shift: models.ConfirmedShift, db: Session) -> rc.CastShiftInput:
    is_help = shift.cast_id is None or shift.help_from_store_id is not None
    if shift.cast_id is not None and shift.cast:
        cast_name = shift.cast.stage_name
        hourly = shift.cast.hourly_rate or 1400
        help_rate = shift.cast.help_hourly_rate
    else:
        cast_name = f"[ヘルプ]{shift.help_cast_name or '不明'}"
        hourly = 1400
        help_rate = None
    help_from_store_name = None
    if shift.help_from_store_id:
        st = db.query(models.Store).filter(models.Store.id == shift.help_from_store_id).first()
        help_from_store_name = st.name if st else None
    return rc.CastShiftInput(
        cast_id=shift.cast_id,
        cast_name=cast_name,
        is_help=bool(is_help),
        help_from_store_name=help_from_store_name,
        actual_start_jst=_to_jst(shift.actual_start),
        actual_end_jst=_to_jst(shift.actual_end),
        is_late=bool(shift.is_late),
        is_absent=bool(shift.is_absent),
        hourly_rate=hourly,
        help_hourly_rate=help_rate,
    )


def _to_staff_input(att: models.StaffAttendance) -> rc.StaffAttendanceInput:
    return rc.StaffAttendanceInput(
        id=att.id,
        name=att.name,
        employee_type=att.employee_type,
        actual_start_jst=_to_jst(att.actual_start),
        actual_end_jst=_to_jst(att.actual_end),
        is_late=bool(att.is_late),
        is_absent=bool(att.is_absent),
    )


# ─────────────────────────────────────────
# データ取得
# ─────────────────────────────────────────

def _fetch_session_tickets(db: Session, session: models.BusinessSession) -> List[models.Ticket]:
    q = db.query(models.Ticket).filter(
        models.Ticket.store_id == session.store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= session.opened_at,
    )
    if session.closed_at:
        q = q.filter(models.Ticket.ended_at <= session.closed_at)
    return q.all()


def _fetch_session_shifts(db: Session, session: models.BusinessSession) -> List[models.ConfirmedShift]:
    business_date = (session.opened_at + timedelta(hours=9)).date()
    return db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.store_id == session.store_id,
        models.ConfirmedShift.date == business_date,
        or_(
            models.ConfirmedShift.actual_start.isnot(None),
            models.ConfirmedShift.is_absent == True,
        ),
    ).all()


def _fetch_session_staff_att(db: Session, session: models.BusinessSession) -> List[models.StaffAttendance]:
    business_date = (session.opened_at + timedelta(hours=9)).date()
    return db.query(models.StaffAttendance).filter(
        models.StaffAttendance.store_id == session.store_id,
        models.StaffAttendance.date == business_date,
    ).all()


# ─────────────────────────────────────────
# 経費 / 日払い 出金パース
# ─────────────────────────────────────────

def _extract_expenses(session: models.BusinessSession) -> dict:
    """expenses_detail から酒類経費・その他経費・出金日払い名一覧を抽出。
    schema 不確定のため、想定される複数キーをフォールバックで読み取る。"""
    detail = session.expenses_detail or {}
    if not isinstance(detail, dict):
        return {"alcohol": 0, "other": 0, "daily_pay_names": set()}

    alcohol = 0
    other = 0
    daily_pay_names = set()

    # 想定される構造1: { "酒類": [{"amount": 1000}, ...], "その他": [...] }
    for key, target in (("酒類", "alcohol"), ("alcohol", "alcohol"),
                        ("その他", "other"), ("other", "other")):
        v = detail.get(key)
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    amt = it.get("amount") or it.get("price") or 0
                    if target == "alcohol":
                        alcohol += int(amt or 0)
                    else:
                        other += int(amt or 0)
        elif isinstance(v, (int, float)):
            if target == "alcohol":
                alcohol += int(v)
            else:
                other += int(v)

    # 想定される構造2: { "withdrawals": [{"type": "日払い", "name": "あむ", ...}] }
    for key in ("withdrawals", "出金", "withdraw"):
        v = detail.get(key)
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    t = it.get("type") or it.get("category") or ""
                    if "日払い" in str(t):
                        nm = it.get("name") or ""
                        if nm:
                            daily_pay_names.add(str(nm).strip())

    return {"alcohol": alcohol, "other": other, "daily_pay_names": daily_pay_names}


# ─────────────────────────────────────────
# 日報 JSON 組み立て
# ─────────────────────────────────────────

VERSION = 1


def build_daily_report_payload(
    db: Session,
    session: models.BusinessSession,
    *,
    generated_by: Optional[int] = None,
) -> dict:
    """指定セッションから日報 JSON を組み立てる"""
    store = db.query(models.Store).filter(models.Store.id == session.store_id).first()
    business_date = (session.opened_at + timedelta(hours=9)).date()

    menu_configs = db.query(models.MenuItemConfig).filter(
        models.MenuItemConfig.store_id == session.store_id,
    ).all()
    label_meta = _menu_label_meta(menu_configs)

    raw_tickets = _fetch_session_tickets(db, session)
    tickets = [_to_ticket_input(t, label_meta) for t in raw_tickets]

    raw_shifts = _fetch_session_shifts(db, session)
    shifts = [_to_shift_input(s, db) for s in raw_shifts]

    raw_staff_att = _fetch_session_staff_att(db, session)
    staff_atts = [_to_staff_input(a) for a in raw_staff_att]

    expenses = _extract_expenses(session)

    # ─── 売上集計 ───
    daily_sales = rc.total_sales(tickets)
    rotation = rc.rotation_summary(tickets)
    sales_block = {
        "total_amount": daily_sales,
        "extension_count": rc.total_extensions(tickets),
        "n_count": rc.total_n_guests(tickets),
        "r_count": rc.total_r_guests(tickets),
        "ticket_count": rc.total_ticket_count(tickets),
        "guest_count": rc.total_guest_count(tickets),
        "avg_per_guest": rc.avg_per_guest(tickets),
        "avg_per_n": rc.avg_per_n(tickets),
        "avg_per_r": rc.avg_per_r(tickets),
        "cast_rotation_total": rotation["total"],
        "cast_rotation_per_ticket": {str(k): v for k, v in rotation["per_ticket"].items()},
        "cast_rotation_per_cast": {str(k): v for k, v in rotation["per_cast"].items()},
        "course_counts": rc.count_by_plan(tickets),
        "motivation": rc.count_by_motivation(tickets),
        "hourly_arrivals": {str(k): v for k, v in rc.hourly_arrivals(tickets).items()},
        "alcohol_expense": expenses["alcohol"],
        "other_expense": expenses["other"],
        "drink_s_total": rc.drink_total_by_type(tickets, "drink_s"),
        "drink_l_total": rc.drink_total_by_type(tickets, "drink_l"),
        "drink_mg_total": rc.drink_total_by_type(tickets, "drink_mg"),
        "champagne_count": rc.champagne_count_total(tickets),
        "champagne_amount": rc.champagne_amount_total(tickets),
        "set_count": rc.total_set_count(tickets),
        "drink_s_per_set": rc.drinks_per_set(tickets, "drink_s"),
        "drink_l_per_set": rc.drinks_per_set(tickets, "drink_l"),
        "drink_mg_per_set": rc.drinks_per_set(tickets, "drink_mg"),
    }

    # ─── キャスト人件費 ───
    cast_payroll_block = rc.cast_payroll_summary(shifts, tickets, daily_sales)

    # ─── 伝票一覧 ───
    ticket_blocks = []
    for t in tickets:
        ticket_blocks.append({
            "id": t.id,
            "table_no": t.table_no,
            "started_at": t.started_at_jst.isoformat() if t.started_at_jst else None,
            "ended_at": t.ended_at_jst.isoformat() if t.ended_at_jst else None,
            "guest_count": t.guest_count,
            "n_count": t.n_count,
            "r_count": t.r_count,
            "extension_count": t.extension_count,
            "rotation_count": rc.rotation_count_for_ticket(t),
            "plan_type": t.plan_type,
            "visit_motivation": t.visit_motivation,
            "customer_name": t.customer_name,
            "total_amount": t.total_amount,
            "cash_amount": t.cash_amount,
            "card_amount": t.card_amount,
            "code_amount": t.code_amount,
            "payment_method": t.payment_method,
            "drink_s": rc.drink_total_by_type([t], "drink_s"),
            "drink_l": rc.drink_total_by_type([t], "drink_l"),
            "drink_mg": rc.drink_total_by_type([t], "drink_mg"),
            "shot_cast": rc.drink_total_by_type([t], "shot_cast"),
            "champagne_groups": [
                {
                    "item_name": group[0].item_name,
                    "unit_price": next((o.unit_price for o in group if o.unit_price > 0), 0),
                    "cast_distribution": next((o.cast_distribution for o in group if o.cast_distribution), None),
                }
                for group in rc.champagne_groups(t)
            ],
        })

    # ─── キャスト勤怠 ───
    cast_blocks = []
    for s in shifts:
        cid = s.cast_id
        # 各キャスト個別データ
        incentive = rc.cast_incentive_total_for(cid, tickets) if cid is not None else 0
        hours = rc.work_hours(s.actual_start_jst, s.actual_end_jst)
        rate = rc.applied_hourly_rate(s)
        base = rc.cast_base_pay(s)
        has_pay = s.cast_name in expenses["daily_pay_names"]
        daily_pay = rc.cast_daily_pay(s, has_payment_record=has_pay) if cid is not None else 0
        perf_2226 = rc.cast_perf_22_26(cid, s, tickets) if cid is not None else None

        # ティッシュ件数（cid のみ・ヘルプキャストは N/A）
        n_tissue = 0
        r_tissue = 0
        for t in tickets:
            if t.visit_motivation == "ティッシュ" and t.motivation_cast_id == cid:
                n_tissue += 1 if t.n_count > 0 else 0
                r_tissue += 1 if t.r_count > 0 else 0

        # キャスト選択あり×インセンティブあり 注文を受けた顧客名一覧
        customer_names = set()
        for t in tickets:
            for o in t.orders:
                if o.canceled or o.cast_id != cid:
                    continue
                if o.cast_required and o.has_incentive:
                    if t.customer_name:
                        customer_names.add(t.customer_name)
                    break

        # シャンパン分配額の計算（incentive_total に含まれているシャンパン分のみ）
        champagne_amount = 0
        champagne_count = 0
        if cid is not None:
            for t in tickets:
                for group in rc.champagne_groups(t):
                    dist_holder = next(
                        (o for o in group if o.cast_distribution),
                        None,
                    )
                    if dist_holder is None:
                        continue
                    back_pool = dist_holder.incentive_amount
                    for entry in dist_holder.cast_distribution:
                        if entry.get("cast_id") == cid:
                            ratio = entry.get("ratio", 0)
                            champagne_amount += int(back_pool * ratio / 100)
                            champagne_count += 1
                            break

        cast_blocks.append({
            "cast_id": cid,
            "cast_name": s.cast_name,
            "is_help": s.is_help,
            "help_from_store_name": s.help_from_store_name,
            "actual_start": s.actual_start_jst.isoformat() if s.actual_start_jst else None,
            "actual_end": s.actual_end_jst.isoformat() if s.actual_end_jst else None,
            "is_late": s.is_late,
            "is_absent": s.is_absent,
            "work_hours": hours,
            "applied_hourly_rate": rate,
            "base_pay": base,
            "incentive_total": incentive,
            "daily_pay": daily_pay,
            "perf_22_26": perf_2226,
            "n_tissue_count": n_tissue,
            "r_tissue_count": r_tissue,
            "customer_names": sorted(customer_names),
            "drink_s": sum(o.quantity for t in tickets for o in t.orders if not o.canceled and o.cast_id == cid and o.item_type == "drink_s"),
            "drink_l": sum(o.quantity for t in tickets for o in t.orders if not o.canceled and o.cast_id == cid and o.item_type == "drink_l"),
            "drink_mg": sum(o.quantity for t in tickets for o in t.orders if not o.canceled and o.cast_id == cid and o.item_type == "drink_mg"),
            "shot_cast": sum(o.quantity for t in tickets for o in t.orders if not o.canceled and o.cast_id == cid and o.item_type == "shot_cast"),
            "champagne_count": champagne_count,
            "champagne_amount": champagne_amount,
        })

    # ─── 社員/アルバイト勤怠 ───
    staff_blocks = []
    for a in staff_atts:
        hours = rc.work_hours(a.actual_start_jst, a.actual_end_jst)
        has_pay = a.name in expenses["daily_pay_names"]
        pay = rc.staff_daily_pay(a, has_payment_record=has_pay)
        staff_blocks.append({
            "id": a.id,
            "name": a.name,
            "employee_type": a.employee_type,
            "actual_start": a.actual_start_jst.isoformat() if a.actual_start_jst else None,
            "actual_end": a.actual_end_jst.isoformat() if a.actual_end_jst else None,
            "is_late": a.is_late,
            "is_absent": a.is_absent,
            "work_hours": hours,
            "daily_pay": pay,
        })

    return {
        "version": VERSION,
        "store_id": session.store_id,
        "store_name": store.name if store else None,
        "business_date": business_date.isoformat(),
        "session_id": session.id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "generated_by": generated_by,
        "sales": sales_block,
        "cast_payroll": cast_payroll_block,
        "tickets": ticket_blocks,
        "cast_attendance": cast_blocks,
        "staff_attendance": staff_blocks,
    }


# ─────────────────────────────────────────
# スナップショット保存
# ─────────────────────────────────────────

def save_snapshot(
    db: Session,
    store_id: int,
    business_date: date,
    payload: dict,
    *,
    generated_by: Optional[int] = None,
) -> models.DailyReportSnapshot:
    """新バージョンとして保存（既存は不変）"""
    latest = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date == business_date,
    ).order_by(models.DailyReportSnapshot.version.desc()).first()
    next_version = (latest.version + 1) if latest else 1

    snap = models.DailyReportSnapshot(
        store_id=store_id,
        business_date=business_date,
        version=next_version,
        payload=payload,
        created_by=generated_by,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def get_latest_snapshot(
    db: Session,
    store_id: int,
    business_date: date,
) -> Optional[models.DailyReportSnapshot]:
    return db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date == business_date,
    ).order_by(models.DailyReportSnapshot.version.desc()).first()
