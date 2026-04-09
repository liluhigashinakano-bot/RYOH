import os
import json
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime, date
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "reports")


class SessionOpen(BaseModel):
    store_id: int
    opening_cash: int = 0
    opening_cash_detail: Optional[Dict[str, int]] = None
    prev_day_diff: int = 0
    operator_name: Optional[str] = None
    event_name: Optional[str] = None
    notes: Optional[str] = None


class SessionClose(BaseModel):
    closing_cash: int = 0
    closing_cash_detail: Optional[Dict[str, int]] = None
    notes: Optional[str] = None
    cash_diff: Optional[int] = None
    expenses_detail: Optional[Dict] = None  # 経費・出金明細
    cash_sales: Optional[int] = None
    card_sales: Optional[int] = None
    code_sales: Optional[int] = None


def _session_dict(s: models.BusinessSession) -> dict:
    return {
        "id": s.id,
        "store_id": s.store_id,
        "date": s.date.isoformat() if s.date else None,
        "opened_at": s.opened_at.isoformat() if s.opened_at else None,
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        "opening_cash": s.opening_cash,
        "opening_cash_detail": s.opening_cash_detail,
        "closing_cash": s.closing_cash,
        "closing_cash_detail": s.closing_cash_detail,
        "prev_day_diff": s.prev_day_diff,
        "sales_snapshot": s.sales_snapshot,
        "operator_name": s.operator_name,
        "event_name": s.event_name,
        "is_closed": s.is_closed,
        "notes": s.notes,
        "cash_diff": s.cash_diff,
        "expenses_detail": s.expenses_detail,
        "cash_sales": s.cash_sales,
        "card_sales": s.card_sales,
        "code_sales": s.code_sales,
        "opened_by_name": s.opened_by_user.name if s.opened_by_user else None,
        "closed_by_name": s.closed_by_user.name if s.closed_by_user else None,
        "store_name": s.store.name if s.store else None,
    }


def _save_report_file(session_data: dict) -> str:
    """営業日報をJSONファイルとして保存する"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    date_str = session_data.get("date", "unknown")
    store_id = session_data.get("store_id", 0)
    store_name = (session_data.get("store_name") or f"store{store_id}").replace(" ", "_")
    filename = f"{date_str}_{store_name}_session{session_data['id']}.json"
    filepath = os.path.join(REPORTS_DIR, filename)
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "session": session_data,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return filepath


@router.get("/dashboard/{store_id}")
def get_dashboard(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ダッシュボード用リアルタイムデータ"""
    from datetime import timedelta

    # アクティブセッション取得
    session = db.query(models.BusinessSession).filter(
        models.BusinessSession.store_id == store_id,
        models.BusinessSession.is_closed == False,
    ).order_by(models.BusinessSession.opened_at.desc()).first()

    # セッション境界
    if session:
        since = session.opened_at
    else:
        # セッション外でも当日営業日データを表示
        now_jst = datetime.utcnow() + timedelta(hours=9)
        if now_jst.hour < 12:
            business_date = now_jst.date() - timedelta(days=1)
        else:
            business_date = now_jst.date()
        since = datetime(business_date.year, business_date.month, business_date.day, 3, 0, 0)

    # 会計済み伝票（セッション開始以降）
    closed_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= since,
    ).all()

    # 未会計伝票（現在オープン中）
    open_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == False,
    ).all()

    def grand_total(t):
        return max(0, (t.total_amount or 0) - (t.discount_amount or 0))

    closed_sales = sum(grand_total(t) for t in closed_tickets)
    open_sales = sum(grand_total(t) for t in open_tickets)
    closed_guests = sum(t.guest_count or 0 for t in closed_tickets)
    open_guests = sum(t.guest_count or 0 for t in open_tickets)

    # 勤務中社員/アルバイト（当日セッション日付のStaffAttendance, actual_end IS NULL, not absent）
    session_date = (since + timedelta(hours=9)).date()
    working_staff = db.query(models.StaffAttendance).filter(
        models.StaffAttendance.store_id == store_id,
        models.StaffAttendance.date == session_date,
        models.StaffAttendance.actual_start.isnot(None),
        models.StaffAttendance.actual_end.is_(None),
        models.StaffAttendance.is_absent == False,
    ).all()

    def bar_hhmm(dt):
        if not dt:
            return None
        jst = dt + timedelta(hours=9)
        h = jst.hour + 24 if jst.hour < 12 else jst.hour
        return f"{h:02d}:{jst.minute:02d}"

    staff_list = [
        {
            "name": s.name,
            "actual_start": bar_hhmm(s.actual_start),
            "is_late": bool(s.is_late),
        }
        for s in working_staff
    ]

    # 勤務中キャスト（当日セッション日付のConfirmedShift, actual_end IS NULL, not absent）
    working_shifts = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.store_id == store_id,
        models.ConfirmedShift.date == session_date,
        models.ConfirmedShift.actual_start.isnot(None),
        models.ConfirmedShift.actual_end.is_(None),
        models.ConfirmedShift.is_absent == False,
    ).all()

    cast_list = []
    for shift in working_shifts:
        if shift.cast_id is not None and shift.cast:
            cast = shift.cast
            cast_list.append({
                "cast_id": cast.id,
                "stage_name": cast.stage_name,
                "rank": cast.rank if isinstance(cast.rank, str) else (cast.rank.value if cast.rank else None),
                "actual_start": bar_hhmm(shift.actual_start),
                "is_late": bool(shift.is_late),
            })
        elif shift.help_cast_name:
            cast_list.append({
                "cast_id": None,
                "stage_name": f"[ヘルプ]{shift.help_cast_name}",
                "rank": None,
                "actual_start": bar_hhmm(shift.actual_start),
                "is_late": bool(shift.is_late),
            })

    return {
        "session": _session_dict(session) if session else None,
        "closed_sales": closed_sales,
        "open_sales": open_sales,
        "closed_groups": len(closed_tickets),
        "closed_guests": closed_guests,
        "open_groups": len(open_tickets),
        "open_guests": open_guests,
        "working_staff": staff_list,
        "working_casts": cast_list,
    }


@router.get("/last-closed")
def get_last_closed_session(store_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """前回終了した営業セッションを取得（翌日の前日過不足金表示用）"""
    session = db.query(models.BusinessSession).filter(
        models.BusinessSession.store_id == store_id,
        models.BusinessSession.is_closed == True,
    ).order_by(models.BusinessSession.closed_at.desc()).first()
    if not session:
        return None
    return _session_dict(session)


@router.get("/current")
def get_current_session(store_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """現在アクティブな営業セッションを取得（なければ null）"""
    session = db.query(models.BusinessSession).filter(
        models.BusinessSession.store_id == store_id,
        models.BusinessSession.is_closed == False,
    ).order_by(models.BusinessSession.opened_at.desc()).first()
    if not session:
        return None
    return _session_dict(session)


@router.get("/list")
def list_sessions(store_id: int, limit: int = 30, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """終了済み営業セッション一覧（日報一覧用）"""
    sessions = db.query(models.BusinessSession).filter(
        models.BusinessSession.store_id == store_id,
        models.BusinessSession.is_closed == True,
    ).order_by(models.BusinessSession.date.desc(), models.BusinessSession.closed_at.desc()).limit(limit).all()
    return [_session_dict(s) for s in sessions]


@router.post("/open")
def open_session(data: SessionOpen, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """営業開始"""
    existing = db.query(models.BusinessSession).filter(
        models.BusinessSession.store_id == data.store_id,
        models.BusinessSession.is_closed == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="既に営業中のセッションがあります")

    # 営業日: 0〜11時は前日扱い（バー営業時間）
    from datetime import timedelta
    now = datetime.utcnow()
    local_hour = (now.hour + 9) % 24  # JST
    today = now.date()
    if local_hour < 12:
        today = now.date() - timedelta(days=1)

    session = models.BusinessSession(
        store_id=data.store_id,
        date=today,
        opening_cash=data.opening_cash,
        opening_cash_detail=data.opening_cash_detail,
        prev_day_diff=data.prev_day_diff,
        operator_name=data.operator_name,
        event_name=data.event_name,
        opened_by=current_user.id,
        notes=data.notes,
        is_closed=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_dict(session)


@router.post("/{session_id}/close")
def close_session(session_id: int, data: SessionClose, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """営業終了"""
    session = db.query(models.BusinessSession).filter(
        models.BusinessSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    if session.is_closed:
        raise HTTPException(status_code=400, detail="既に終了済みのセッションです")

    closed_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == session.store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= session.opened_at,
    ).all()

    def _grand(t):
        sk = sum(
            abs(i.amount) for i in (t.order_items or [])
            if i.item_name and (
                i.item_name.startswith('先会計') or
                i.item_name.startswith('分割清算') or
                i.item_name.startswith('値引き')
            ) and not i.canceled_at
        )
        sub = (t.total_amount or 0) + sk
        return round(sub * 1.21) - sk

    sales = sum(_grand(t) for t in closed_tickets)

    session.closed_at = datetime.utcnow()
    session.closing_cash = data.closing_cash
    session.closing_cash_detail = data.closing_cash_detail
    session.sales_snapshot = sales
    session.closed_by = current_user.id
    session.is_closed = True
    session.cash_diff = data.cash_diff
    session.expenses_detail = data.expenses_detail
    session.cash_sales = data.cash_sales
    session.card_sales = data.card_sales
    session.code_sales = data.code_sales
    if data.notes:
        parts = [p for p in [session.notes, data.notes] if p]
        session.notes = '\n'.join(parts)

    db.commit()
    db.refresh(session)

    # 当日の勤怠記録をクリア（actual_start/actual_end/is_late/is_absent をリセット）
    from datetime import timedelta
    from sqlalchemy import or_
    session_date_jst = (session.opened_at + timedelta(hours=9)).date()
    shifts_to_clear = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.store_id == session.store_id,
        models.ConfirmedShift.date == session_date_jst,
        or_(
            models.ConfirmedShift.actual_start.isnot(None),
            models.ConfirmedShift.is_absent == True,
        )
    ).all()

    def _dt_to_bar_hhmm_snap(dt: datetime) -> str:
        jst = dt + timedelta(hours=9)
        h, m = jst.hour, jst.minute
        display_h = h + 24 if h < 12 else h
        return f"{display_h:02d}:{m:02d}"

    # クリア前に勤怠スナップショットを expenses_detail に埋め込んで保存
    snap: dict = {}
    for shift in shifts_to_clear:
        if shift.cast_id is not None:
            key = str(shift.cast_id)
            snap[key] = {
                "actual_start": _dt_to_bar_hhmm_snap(shift.actual_start) if shift.actual_start else None,
                "actual_end": _dt_to_bar_hhmm_snap(shift.actual_end) if shift.actual_end else None,
                "is_late": bool(shift.is_late),
                "is_absent": bool(shift.is_absent),
            }
        elif shift.help_cast_name:
            key = f"h_{shift.id}"
            snap[key] = {
                "help_cast_name": shift.help_cast_name,
                "actual_start": _dt_to_bar_hhmm_snap(shift.actual_start) if shift.actual_start else None,
                "actual_end": _dt_to_bar_hhmm_snap(shift.actual_end) if shift.actual_end else None,
                "is_late": bool(shift.is_late),
                "is_absent": bool(shift.is_absent),
            }
    # 社員/アルバイト勤怠もクリア前にスナップショット
    staff_to_clear = db.query(models.StaffAttendance).filter(
        models.StaffAttendance.store_id == session.store_id,
        models.StaffAttendance.date == session_date_jst,
    ).all()
    staff_snap = [
        {
            "name": sr.name,
            "actual_start": _dt_to_bar_hhmm_snap(sr.actual_start) if sr.actual_start else None,
            "actual_end": _dt_to_bar_hhmm_snap(sr.actual_end) if sr.actual_end else None,
            "is_late": bool(sr.is_late),
            "is_absent": bool(sr.is_absent),
        }
        for sr in staff_to_clear
    ]

    # 既存の expenses_detail に "_attendance" / "_staff_attendance" キーで追記
    existing_detail = session.expenses_detail or {}
    session.expenses_detail = {**existing_detail, "_attendance": snap, "_staff_attendance": staff_snap}
    db.commit()
    db.refresh(session)

    # 日報スナップショット生成（勤怠クリア前なので実データが取れる）
    try:
        from ..services.report_builder import build_daily_report_full, save_snapshot
        from datetime import timedelta as _td
        payload, raw_inputs = build_daily_report_full(db, session, generated_by=current_user.id)
        biz_date = (session.opened_at + _td(hours=9)).date()
        save_snapshot(
            db, session.store_id, biz_date, payload,
            raw_inputs=raw_inputs, generated_by=current_user.id,
        )
    except Exception as e:
        # 日報生成失敗してもセッションクローズは成功させる
        print(f"[WARNING] Failed to build daily report snapshot: {e}")
        import traceback
        traceback.print_exc()

    # 勤怠クリア（snapshot 生成後に実行）
    for shift in shifts_to_clear:
        shift.actual_start = None
        shift.actual_end = None
        shift.is_late = False
        shift.is_absent = False

    for sr in staff_to_clear:
        db.delete(sr)
    db.commit()

    # 既存: 日報JSONファイルを保存（旧仕組み・並行運用）
    try:
        _save_report_file(_session_dict(session))
    except Exception as e:
        print(f"[WARNING] Failed to save report file: {e}")

    return _session_dict(session)


CAST_DRINK_TYPES = ("drink_s", "drink_l", "drink_mg", "shot_cast", "champagne")
DRINK_UNIT_PRICE = {"drink_s": 100, "drink_l": 400, "drink_mg": 800, "shot_cast": 300}


def _build_incentive_map(store_id: int, db: Session) -> dict:
    """store_idのIncentiveConfigから drink_type → back計算関数 を返す"""
    configs = db.query(models.IncentiveConfig).filter(
        models.IncentiveConfig.store_id == store_id
    ).all()
    result = {}
    for c in configs:
        if c.incentive_mode == "fixed" and c.fixed_amount is not None:
            result[c.drink_type] = ("fixed", c.fixed_amount)
        else:
            result[c.drink_type] = ("percent", c.rate or 10)
    return result


def _calc_back(drink_type: str, unit_price: int, quantity: int, incentive_map: dict) -> int:
    """1品目のキャストバック額を計算"""
    cfg = incentive_map.get(drink_type)
    if cfg is None:
        # フォールバック: 旧来のハードコード値
        return DRINK_UNIT_PRICE.get(drink_type, 0) * quantity
    mode, value = cfg
    if mode == "fixed":
        return value * quantity
    else:  # percent
        return int(unit_price * value / 100) * quantity


@router.get("/{session_id}/cast-drinks")
def get_session_cast_drinks(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """営業セッション内のキャスト別ドリンク集計"""
    session = db.query(models.BusinessSession).filter(models.BusinessSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    # インセンティブ設定を取得
    incentive_map = _build_incentive_map(session.store_id, db)

    # セッション内の伝票を取得（get_session_ticketsと同じフィルター）
    query = db.query(models.Ticket).filter(
        models.Ticket.store_id == session.store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= session.opened_at,
    )
    if session.closed_at:
        query = query.filter(models.Ticket.ended_at <= session.closed_at)
    tickets = query.all()

    cast_map: dict = {}
    # 通常メニュー（非シャンパン）のインセンティブ累計を別管理
    nonchamp_amount: dict = defaultdict(int)

    def _ensure_cast(cid: int, item: models.OrderItem) -> None:
        if cid not in cast_map:
            cast_name = item.cast.stage_name if item.cast else f"Cast{cid}"
            cast_map[cid] = {
                "cast_id": cid,
                "cast_name": cast_name,
                "drink_s": 0,
                "drink_l": 0,
                "drink_mg": 0,
                "shot_cast": 0,
                "champagne": 0,
                "champagne_amount": 0,
            }

    # 集計用ヘルパー: snapshot 優先・無ければ旧計算でフォールバック
    def _amount_for_item(item: models.OrderItem) -> int:
        snap = item.incentive_snapshot or {}
        amt = snap.get("calculated_amount") if isinstance(snap, dict) else None
        if amt is not None:
            return int(amt)
        # フォールバック（snapshot が無い古いデータ用）
        return _calc_back(item.item_type, item.unit_price or 0, item.quantity or 0, incentive_map)

    for ticket in tickets:
        valid_items = [
            i for i in ticket.order_items
            if i.canceled_at is None and i.cast_id is not None and i.item_type in CAST_DRINK_TYPES
        ]

        # S/L/MG/shot_cast/custom_menu: 数量集計 + snapshot 金額累積
        for item in valid_items:
            if item.item_type == "champagne":
                continue
            _ensure_cast(item.cast_id, item)
            if item.item_type in ("drink_s", "drink_l", "drink_mg", "shot_cast"):
                cast_map[item.cast_id][item.item_type] += item.quantity
            # custom_menu 含むすべての非シャンパンメニューのインセンティブ金額を累積
            nonchamp_amount[item.cast_id] += _amount_for_item(item)

        # シャンパン
        # 新形式: cast_distribution が存在する行はそれで配分
        # 旧形式: cast_distribution が無いグループは item_name パースにフォールバック
        champ_groups: dict = defaultdict(list)
        for item in valid_items:
            if item.item_type == "champagne":
                champ_groups[item.item_name or ""].append(item)

        for item_name, items in champ_groups.items():
            items_sorted = sorted(items, key=lambda i: i.id)

            # cast_distribution を持つ代表行を探す（同一グループでは同じ JSON が入っている想定）
            dist_holder = next(
                (i for i in items_sorted if isinstance(i.cast_distribution, list) and i.cast_distribution),
                None
            )

            if dist_holder is None:
                # cast_distribution が無いシャンパンは集計対象外
                # （Phase A-2 移行スクリプトで全データ移行済み）
                continue

            # cast_distribution ベースで配分
            snap = dist_holder.incentive_snapshot or {}
            back_pool = int(snap.get("calculated_amount") or 0)
            # snapshot が無い場合は unit_price から再計算
            if back_pool == 0:
                price_item = next((i for i in items_sorted if (i.unit_price or 0) > 0), None)
                unit_price = price_item.unit_price if price_item else 0
                champ_cfg = incentive_map.get("champagne")
                if champ_cfg:
                    mode, value = champ_cfg
                    back_pool = int((unit_price * value / 100) if mode == "percent" else value)
            # 各 cast_id に分配
            for entry in dist_holder.cast_distribution:
                cid = entry.get("cast_id")
                ratio = entry.get("ratio") or 0
                if cid is None:
                    continue
                if cid not in cast_map:
                    cast_obj = db.query(models.Cast).filter(models.Cast.id == cid).first()
                    cast_name = cast_obj.stage_name if cast_obj else f"Cast{cid}"
                    cast_map[cid] = {
                        "cast_id": cid, "cast_name": cast_name,
                        "drink_s": 0, "drink_l": 0, "drink_mg": 0,
                        "shot_cast": 0, "champagne": 0, "champagne_amount": 0,
                    }
                cast_map[cid]["champagne"] += 1
                cast_map[cid]["champagne_amount"] += int(back_pool * ratio / 100)

    # 勤怠情報を取得（クローズ済みはスナップショット、オープン中はライブデータ）
    from datetime import timedelta
    from sqlalchemy import or_

    # スナップショット: cast_id(str) → {actual_start, actual_end, is_late, is_absent}
    # expenses_detail の "_attendance" キーに保存されている
    snap: dict = (session.expenses_detail or {}).get("_attendance", {})

    def _empty_cast_entry(cast_id, cast_name):
        return {
            "cast_id": cast_id,
            "cast_name": cast_name,
            "drink_s": 0,
            "drink_l": 0,
            "drink_mg": 0,
            "shot_cast": 0,
            "champagne": 0,
            "champagne_amount": 0,
        }

    if session.is_closed and snap:
        # スナップショットから勤怠があるがドリンクがないキャストを追加
        for snap_key, att in snap.items():
            if snap_key.startswith("h_"):
                # ヘルプキャスト
                help_name = att.get("help_cast_name", "ヘルプ")
                cast_name = f"[ヘルプ]{help_name}"
                if snap_key not in cast_map:
                    cast_map[snap_key] = _empty_cast_entry(None, cast_name)
            else:
                cid = int(snap_key)
                if cid not in cast_map:
                    cast_obj = db.query(models.Cast).filter(models.Cast.id == cid).first()
                    cast_name = cast_obj.stage_name if cast_obj else f"Cast{cid}"
                    cast_map[cid] = _empty_cast_entry(cid, cast_name)

        # 合計金額と勤怠情報を付与
        for key, entry in cast_map.items():
            entry["total_amount"] = nonchamp_amount.get(key, 0) + entry["champagne_amount"]
            snap_key = f"h_{key}" if key is None or (isinstance(key, str) and key.startswith("h_")) else str(key)
            att = snap.get(snap_key, snap.get(str(key), {}))
            entry["actual_start"] = att.get("actual_start")
            entry["actual_end"] = att.get("actual_end")
            entry["is_late"] = att.get("is_late", False)
            entry["is_absent"] = att.get("is_absent", False)
    else:
        # オープン中またはスナップショットなし: ライブの ConfirmedShift を参照
        session_date_jst = (session.opened_at + timedelta(hours=9)).date()
        shifts = db.query(models.ConfirmedShift).filter(
            models.ConfirmedShift.store_id == session.store_id,
            models.ConfirmedShift.date == session_date_jst,
            or_(
                models.ConfirmedShift.actual_start.isnot(None),
                models.ConfirmedShift.is_absent == True,
            )
        ).all()

        def _dt_to_bar_hhmm(dt: datetime) -> str:
            jst = dt + timedelta(hours=9)
            h, m = jst.hour, jst.minute
            display_h = h + 24 if h < 12 else h
            return f"{display_h:02d}:{m:02d}"

        for shift in shifts:
            if shift.cast_id is not None:
                cid = shift.cast_id
                if cid not in cast_map:
                    cast_name = shift.cast.stage_name if shift.cast else f"Cast{cid}"
                    cast_map[cid] = _empty_cast_entry(cid, cast_name)
            elif shift.help_cast_name:
                key = f"h_{shift.id}"
                if key not in cast_map:
                    cast_map[key] = _empty_cast_entry(None, f"[ヘルプ]{shift.help_cast_name}")

        # cast_id → shift のマップ（通常キャスト用）
        shift_map = {s.cast_id: s for s in shifts if s.cast_id is not None}
        # help shift: key → shift
        help_shift_map = {f"h_{s.id}": s for s in shifts if s.cast_id is None}

        for key, entry in cast_map.items():
            entry["total_amount"] = nonchamp_amount.get(key, 0) + entry["champagne_amount"]
            if isinstance(key, str) and key.startswith("h_"):
                shift = help_shift_map.get(key)
            else:
                shift = shift_map.get(key)
            entry["actual_start"] = _dt_to_bar_hhmm(shift.actual_start) if shift and shift.actual_start else None
            entry["actual_end"] = _dt_to_bar_hhmm(shift.actual_end) if shift and shift.actual_end else None
            entry["is_late"] = bool(shift.is_late) if shift else False
            entry["is_absent"] = bool(shift.is_absent) if shift else False

    return sorted(cast_map.values(), key=lambda x: x["cast_name"])


@router.get("/{session_id}/staff-attendance")
def get_session_staff_attendance(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """営業セッションの社員/アルバイト勤怠一覧"""
    session = db.query(models.BusinessSession).filter(models.BusinessSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    from datetime import timedelta

    # クローズ済みはスナップショットを返す
    if session.is_closed:
        snap = (session.expenses_detail or {}).get("_staff_attendance", [])
        return snap

    # オープン中はライブデータ
    session_date_jst = (session.opened_at + timedelta(hours=9)).date()
    records = db.query(models.StaffAttendance).filter(
        models.StaffAttendance.store_id == session.store_id,
        models.StaffAttendance.date == session_date_jst,
    ).order_by(models.StaffAttendance.created_at).all()

    def _dt_to_bar(dt) -> str:
        jst = dt + timedelta(hours=9)
        h, m = jst.hour, jst.minute
        display_h = h + 24 if h < 12 else h
        return f"{display_h:02d}:{m:02d}"

    return [
        {
            "name": r.name,
            "actual_start": _dt_to_bar(r.actual_start) if r.actual_start else None,
            "actual_end": _dt_to_bar(r.actual_end) if r.actual_end else None,
            "is_late": bool(r.is_late),
            "is_absent": bool(r.is_absent),
        }
        for r in records
    ]


@router.get("/{session_id}/tickets")
def get_session_tickets(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """営業セッション内の伝票一覧"""
    session = db.query(models.BusinessSession).filter(models.BusinessSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    query = db.query(models.Ticket).filter(
        models.Ticket.store_id == session.store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= session.opened_at,
    )
    if session.closed_at:
        query = query.filter(models.Ticket.ended_at <= session.closed_at)
    tickets = query.order_by(models.Ticket.ended_at).all()
    result = []
    for t in tickets:
        # 先会計・分割清算で支払い済みの金額（負の注文として記録されている）
        senkaikei_paid = sum(
            abs(i.amount) for i in (t.order_items or [])
            if i.canceled_at is None
            and i.item_name
            and (i.item_name.startswith('先会計') or i.item_name.startswith('分割清算'))
        )
        # 実際の支払い総額 = クローズ時の支払い + 先会計済み額
        actual_paid = (t.cash_amount or 0) + (t.card_amount or 0) + (t.code_amount or 0) + senkaikei_paid
        result.append({
            "id": t.id,
            "table_no": t.table_no,
            "guest_count": t.guest_count or 1,
            "plan_type": t.plan_type,
            "visit_type": t.visit_type,
            "customer_name": t.customer.name if t.customer else None,
            "total_amount": t.total_amount,
            "actual_paid": actual_paid,
            "payment_method": t.payment_method.value if t.payment_method else None,
            "cash_amount": t.cash_amount or 0,
            "card_amount": t.card_amount or 0,
            "code_amount": t.code_amount or 0,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
        })
    return result
