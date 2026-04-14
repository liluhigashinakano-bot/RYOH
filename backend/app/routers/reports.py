"""
日報・月報の表示API。

エンドポイント:
- GET  /api/reports/daily/latest          : 指定 store/date の最新版を返す
- GET  /api/reports/daily/versions        : 指定 store/date の全バージョン一覧
- GET  /api/reports/daily/{snapshot_id}   : 特定スナップショットを取得
- POST /api/reports/daily/regenerate      : 指定 session_id から再生成（新バージョン）
- GET  /api/reports/monthly               : 月報集計（指定 store/year/month）
"""
from datetime import date as date_cls, datetime, timedelta
from typing import Optional
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from .. import models
from ..auth import get_current_user
from ..services.report_builder import (
    build_daily_report_payload,
    build_daily_report_full,
    regenerate_from_snapshot,
    save_snapshot,
    get_latest_snapshot,
)


router = APIRouter(prefix="/api/reports", tags=["reports"])


# ─────────────────────────────────────────
# 旧スナップショット補完 (シャンパン額・カスタムメニュー列の追記)
# ─────────────────────────────────────────

def _enrich_legacy_payload(db: Session, payload: dict, *, force: bool = False) -> dict:
    """過去スナップショットに custom_drink_columns / シャンパン額 / custom_drinks を
    追記して返す（破壊しない）。
    - すでに新フォーマットで force=False なら触らない
    - force=True なら新フォーマットでもシャンパン関連と custom_drinks を上書き再計算
    - DBの tickets/orders/menu_configs/incentive_configs を参照して再計算
    """
    if not isinstance(payload, dict):
        return payload
    has_custom_cols = "custom_drink_columns" in payload
    sample_cast = (payload.get("cast_attendance") or [None])[0]
    has_champ_amount = (
        sample_cast is not None and "champagne_amount" in sample_cast
    )
    if has_custom_cols and has_champ_amount and not force:
        return payload  # 新フォーマット、補完不要

    store_id = payload.get("store_id")
    if not store_id:
        return payload

    # メニュー設定 (custom_menu の cast_required×has_incentive を抽出)
    menu_configs = db.query(models.MenuItemConfig).filter(
        models.MenuItemConfig.store_id == store_id,
    ).all()
    from ..services.report_builder import _assign_short_names
    custom_menu_labels = sorted({
        m.label for m in menu_configs
        if m.is_active and m.cast_required and m.has_incentive
    })
    custom_short_map = _assign_short_names(custom_menu_labels)
    custom_drink_columns = [
        {"label": l, "short": custom_short_map[l]} for l in custom_menu_labels
    ]

    # インセンティブ設定 (シャンパン用)
    from ..services.incentive import build_incentive_map, strip_cast_suffix
    imap = build_incentive_map(db, store_id)
    champ_cfg = imap.get("champagne")  # (mode, value) | None

    # ticket_id → ORM tickets / order_items
    ticket_blocks = payload.get("tickets") or []
    ticket_ids = [t.get("id") for t in ticket_blocks if t.get("id")]
    if not ticket_ids:
        # 触らず返す
        new = dict(payload)
        new.setdefault("custom_drink_columns", custom_drink_columns)
        return new

    orm_tickets = db.query(models.Ticket).filter(models.Ticket.id.in_(ticket_ids)).all()
    orm_by_id = {t.id: t for t in orm_tickets}

    def _champ_back_pool(group_items: list) -> int:
        """グループのバックプール額。snapshot 優先・無ければ incentive 設定で再計算。"""
        # snapshot 優先
        for it in group_items:
            snap = it.incentive_snapshot if isinstance(it.incentive_snapshot, dict) else None
            if snap and snap.get("calculated_amount"):
                return int(snap["calculated_amount"])
        # fallback
        if not champ_cfg:
            return 0
        mode, value = champ_cfg
        price_item = next((i for i in group_items if (i.unit_price or 0) > 0), None)
        unit_price = price_item.unit_price if price_item else 0
        return int((unit_price * value / 100) if mode == "percent" else value)

    def _custom_drinks_for(orders, label_filter_cast_id=None) -> dict:
        """orders から custom_menu のラベル別数量を集計。略称キー。"""
        out = {}
        for label in custom_menu_labels:
            short = custom_short_map[label]
            qty = 0
            for o in orders:
                if o.canceled_at is not None:
                    continue
                if o.item_type != "custom_menu":
                    continue
                if label_filter_cast_id is not None and o.cast_id != label_filter_cast_id:
                    continue
                if strip_cast_suffix(o.item_name or "") == label:
                    qty += o.quantity or 0
            out[short] = qty
        return out

    # 接客中会計の最終キャストを ORM から推定する
    def _closing_cast_id(ot) -> Optional[int]:
        # CastAssignment 優先
        if ot.assignments:
            valid = [a for a in ot.assignments if a.cast_id is not None and a.started_at is not None]
            if valid:
                latest = max(valid, key=lambda a: a.started_at)
                return latest.cast_id
        # フォールバック: キャスト選択ありの注文の最後
        from ..services.report_calc import OrderInput  # 不要だけど明示
        from ..services.incentive import strip_cast_suffix as _scs  # noqa
        cast_orders = []
        for o in (ot.order_items or []):
            if o.canceled_at is not None or o.cast_id is None:
                continue
            mtype = o.item_type
            if mtype in ("drink_s", "drink_l", "drink_mg", "shot_cast", "champagne"):
                cast_orders.append(o)
            elif mtype == "custom_menu":
                label = strip_cast_suffix(o.item_name or "")
                meta = next((m for m in menu_configs if m.label == label and m.cast_required), None)
                if meta is not None:
                    cast_orders.append(o)
        if not cast_orders:
            return None
        last = max(cast_orders, key=lambda o: (o.created_at or datetime.min, o.id))
        return last.cast_id

    closing_counts_legacy: dict = defaultdict(int)
    closing_cid_by_ticket: dict = {}
    for ot in orm_tickets:
        cid = _closing_cast_id(ot)
        closing_cid_by_ticket[ot.id] = cid
        if cid is not None:
            closing_counts_legacy[cid] += 1

    # ─── ticket_blocks 補完 ───
    new_ticket_blocks = []
    for tb in ticket_blocks:
        nt = dict(tb)
        ot = orm_by_id.get(tb.get("id"))
        if ot is None:
            new_ticket_blocks.append(nt)
            continue
        active_orders = [o for o in (ot.order_items or []) if o.canceled_at is None]
        # シャンパングループ
        groups: dict = defaultdict(list)
        for o in active_orders:
            if o.item_type == "champagne":
                groups[o.item_name or ""].append(o)
        champ_count = len(groups)
        champ_amount = 0
        for items in groups.values():
            for it in items:
                if (it.unit_price or 0) > 0:
                    champ_amount += (it.unit_price or 0) * (it.quantity or 0)
        closing_cid = closing_cid_by_ticket.get(ot.id)
        if force:
            nt["champagne_count"] = champ_count
            nt["champagne_amount"] = champ_amount
            nt["custom_drinks"] = _custom_drinks_for(active_orders)
            nt["closing_cast_id"] = closing_cid
        else:
            nt.setdefault("champagne_count", champ_count)
            nt.setdefault("champagne_amount", champ_amount)
            nt.setdefault("custom_drinks", _custom_drinks_for(active_orders))
            nt.setdefault("closing_cast_id", closing_cid)
        new_ticket_blocks.append(nt)

    # ─── cast_attendance 補完 ───
    new_cast_blocks = []
    for cb in (payload.get("cast_attendance") or []):
        nc = dict(cb)
        cid = cb.get("cast_id")
        # シャンパン本数・額 (このキャストの分配額)
        champ_count = 0
        champ_amount = 0
        if cid is not None:
            for ot in orm_tickets:
                active = [o for o in (ot.order_items or []) if o.canceled_at is None and o.item_type == "champagne"]
                groups: dict = defaultdict(list)
                for o in active:
                    groups[o.item_name or ""].append(o)
                for items in groups.values():
                    dist_holder = next(
                        (i for i in items if isinstance(i.cast_distribution, list) and i.cast_distribution),
                        None
                    )
                    if not dist_holder:
                        continue
                    if not any((e.get("cast_id") == cid) for e in dist_holder.cast_distribution):
                        continue
                    back_pool = _champ_back_pool(items)
                    for entry in dist_holder.cast_distribution:
                        if entry.get("cast_id") == cid:
                            ratio = entry.get("ratio") or 0
                            champ_amount += int(back_pool * ratio / 100)
                            champ_count += 1
                            break
        # custom_drinks
        cd_total = {}
        if cid is not None:
            cd_total = {short: 0 for short in custom_short_map.values()}
            for ot in orm_tickets:
                for short, qty in _custom_drinks_for(ot.order_items or [], label_filter_cast_id=cid).items():
                    cd_total[short] = cd_total.get(short, 0) + qty
        cl_count = closing_counts_legacy.get(cid, 0) if cid is not None else 0
        if force:
            nc["champagne_count"] = champ_count
            nc["champagne_amount"] = champ_amount
            nc["custom_drinks"] = cd_total
            nc["closing_count"] = cl_count
        else:
            nc.setdefault("champagne_count", champ_count)
            nc.setdefault("champagne_amount", champ_amount)
            nc.setdefault("custom_drinks", cd_total)
            nc.setdefault("closing_count", cl_count)
        new_cast_blocks.append(nc)

    # 出勤外キャスト（シャンパン分配 or 接客中会計）エントリを追加
    existing_cids = {c.get("cast_id") for c in new_cast_blocks if c.get("cast_id") is not None}
    extra_cids: set = set()
    for ot in orm_tickets:
        for o in (ot.order_items or []):
            if o.canceled_at is not None or o.item_type != "champagne":
                continue
            if not isinstance(o.cast_distribution, list):
                continue
            for entry in o.cast_distribution:
                cid = entry.get("cast_id")
                if cid is not None and cid not in existing_cids:
                    extra_cids.add(cid)
    for cid in closing_counts_legacy.keys():
        if cid not in existing_cids:
            extra_cids.add(cid)
    if extra_cids:
        extra_casts = db.query(models.Cast).filter(models.Cast.id.in_(extra_cids)).all()
        cast_map = {c.id: c for c in extra_casts}
        for cid in sorted(extra_cids):
            cobj = cast_map.get(cid)
            if cobj is None:
                continue
            champ_count = 0
            champ_amount = 0
            for ot in orm_tickets:
                active = [o for o in (ot.order_items or []) if o.canceled_at is None and o.item_type == "champagne"]
                groups: dict = defaultdict(list)
                for o in active:
                    groups[o.item_name or ""].append(o)
                for items in groups.values():
                    dist_holder = next(
                        (i for i in items if isinstance(i.cast_distribution, list) and i.cast_distribution),
                        None
                    )
                    if not dist_holder:
                        continue
                    if not any((e.get("cast_id") == cid) for e in dist_holder.cast_distribution):
                        continue
                    back_pool = _champ_back_pool(items)
                    for entry in dist_holder.cast_distribution:
                        if entry.get("cast_id") == cid:
                            ratio = entry.get("ratio") or 0
                            champ_amount += int(back_pool * ratio / 100)
                            champ_count += 1
                            break
            new_cast_blocks.append({
                "cast_id": cid,
                "cast_name": cobj.stage_name,
                "is_help": False,
                "is_off_shift": True,
                "help_from_store_name": None,
                "actual_start": None,
                "actual_end": None,
                "is_late": False,
                "is_absent": False,
                "work_hours": 0,
                "applied_hourly_rate": 0,
                "base_pay": 0,
                "incentive_total": champ_amount,
                "daily_pay": 0,
                "perf_22_26": None,
                "n_tissue_count": 0,
                "r_tissue_count": 0,
                "customer_names": [],
                "drink_s": 0,
                "drink_l": 0,
                "drink_mg": 0,
                "shot_cast": 0,
                "champagne_count": champ_count,
                "champagne_amount": champ_amount,
                "closing_count": closing_counts_legacy.get(cid, 0),
                "custom_drinks": {short: 0 for short in custom_short_map.values()},
            })

    new_payload = dict(payload)
    new_payload["custom_drink_columns"] = custom_drink_columns
    new_payload["tickets"] = new_ticket_blocks
    new_payload["cast_attendance"] = new_cast_blocks
    return new_payload


# ─────────────────────────────────────────
# 日報
# ─────────────────────────────────────────

@router.get("/daily/latest")
def get_daily_latest(
    store_id: int = Query(...),
    date: date_cls = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定 store_id × business_date の最新版日報を返す"""
    snap = get_latest_snapshot(db, store_id, date)
    if snap is None:
        raise HTTPException(status_code=404, detail="日報が見つかりません")
    return {
        "id": snap.id,
        "store_id": snap.store_id,
        "business_date": snap.business_date.isoformat(),
        "version": snap.version,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "created_by": snap.created_by,
        "payload": _enrich_legacy_payload(db, snap.payload),
        "has_raw_inputs": bool(snap.raw_inputs),
    }


@router.get("/daily/versions")
def get_daily_versions(
    store_id: int = Query(...),
    date: date_cls = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定 store_id × business_date の全バージョン一覧（payload は除外）"""
    rows = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date == date,
    ).order_by(models.DailyReportSnapshot.version.desc()).all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by": r.created_by,
        }
        for r in rows
    ]


@router.get("/daily/list")
def list_daily_reports(
    store_id: int = Query(...),
    start: Optional[date_cls] = Query(None),
    end: Optional[date_cls] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定店舗の日報一覧（最新版のみ・期間絞り込み可）"""
    q = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
    )
    if start:
        q = q.filter(models.DailyReportSnapshot.business_date >= start)
    if end:
        q = q.filter(models.DailyReportSnapshot.business_date <= end)
    rows = q.order_by(
        models.DailyReportSnapshot.business_date.desc(),
        models.DailyReportSnapshot.version.desc(),
    ).all()

    # 同じ business_date は最新版のみ残す
    seen = set()
    result = []
    for r in rows:
        if r.business_date in seen:
            continue
        seen.add(r.business_date)
        sales = (r.payload or {}).get("sales", {})
        result.append({
            "id": r.id,
            "business_date": r.business_date.isoformat(),
            "version": r.version,
            "total_amount": sales.get("total_amount", 0),
            "ticket_count": sales.get("ticket_count", 0),
            "guest_count": sales.get("guest_count", 0),
        })
    return result


@router.get("/daily/{snapshot_id}")
def get_daily_by_id(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    snap = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="スナップショットが見つかりません")
    return {
        "id": snap.id,
        "store_id": snap.store_id,
        "business_date": snap.business_date.isoformat(),
        "version": snap.version,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "created_by": snap.created_by,
        "payload": _enrich_legacy_payload(db, snap.payload),
    }


class UpdateTissueRequest(BaseModel):
    snapshot_id: int
    cast_index: int  # cast_performance配列のインデックス
    tissue_count: int
    operator_name: Optional[str] = None


@router.post("/daily/update-tissue")
def update_tissue_count(
    data: UpdateTissueRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """日報のティッシュ枚数を修正"""
    snap = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.id == data.snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="スナップショットが見つかりません")
    payload = snap.payload or {}
    casts = payload.get("cast_attendance", [])
    if data.cast_index < 0 or data.cast_index >= len(casts):
        raise HTTPException(status_code=400, detail="キャストインデックスが不正です")
    old_count = casts[data.cast_index].get("tissue_count", 0)
    casts[data.cast_index]["tissue_count"] = data.tissue_count
    payload["cast_attendance"] = casts
    snap.payload = payload
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(snap, "payload")
    # 変更ログ記録
    cast_name = casts[data.cast_index].get("cast_name", "不明")
    log = models.OrderItemLog(
        store_id=snap.store_id, action='update_tissue',
        item_name=f"ティッシュ枚数修正: {cast_name} {old_count}→{data.tissue_count}",
        operator_name=data.operator_name,
        changed_by=current_user.id,
    )
    db.add(log)
    db.commit()
    return {"message": "ティッシュ枚数を更新しました"}


class RegenerateRequest(BaseModel):
    snapshot_id: int


class BulkRegenerateRequest(BaseModel):
    store_id: Optional[int] = None
    year: Optional[int] = None
    month: Optional[int] = None


@router.post("/daily/regenerate-bulk")
def regenerate_bulk(
    data: BulkRegenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定範囲の日報を一括再生成する（各営業日の最新版 raw_inputs を使う）"""
    from sqlalchemy import func
    q = db.query(
        models.DailyReportSnapshot.store_id,
        models.DailyReportSnapshot.business_date,
        func.max(models.DailyReportSnapshot.version).label("max_v"),
    )
    if data.store_id:
        q = q.filter(models.DailyReportSnapshot.store_id == data.store_id)
    if data.year and data.month:
        from datetime import date as _date
        start = _date(data.year, data.month, 1)
        end = _date(data.year + (1 if data.month == 12 else 0),
                    1 if data.month == 12 else data.month + 1, 1)
        q = q.filter(
            models.DailyReportSnapshot.business_date >= start,
            models.DailyReportSnapshot.business_date < end,
        )
    latest_keys = q.group_by(
        models.DailyReportSnapshot.store_id,
        models.DailyReportSnapshot.business_date,
    ).all()

    regenerated, skipped, failed = 0, 0, 0
    for store_id, bdate, max_v in latest_keys:
        snap = db.query(models.DailyReportSnapshot).filter(
            models.DailyReportSnapshot.store_id == store_id,
            models.DailyReportSnapshot.business_date == bdate,
            models.DailyReportSnapshot.version == max_v,
        ).first()
        if not snap or not snap.raw_inputs:
            skipped += 1
            continue
        try:
            payload, raw_inputs = regenerate_from_snapshot(db, snap, generated_by=current_user.id)
            save_snapshot(db, snap.store_id, snap.business_date, payload,
                          raw_inputs=raw_inputs, generated_by=current_user.id)
            regenerated += 1
        except Exception:
            failed += 1
            continue
    return {
        "message": "一括再生成が完了しました",
        "regenerated": regenerated,
        "skipped": skipped,
        "failed": failed,
        "total": len(latest_keys),
    }


@router.post("/daily/regenerate")
def regenerate_daily(
    data: RegenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定スナップショットの raw_inputs を元に日報を再構築し、新バージョンとして保存。
    raw_inputs が無い古いスナップショットは再生成不可。"""
    snap = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.id == data.snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="スナップショットが見つかりません")
    if not snap.raw_inputs:
        raise HTTPException(
            status_code=400,
            detail="このスナップショットには再生成用データがありません（古い形式）",
        )
    try:
        payload, raw_inputs = regenerate_from_snapshot(db, snap, generated_by=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    new_snap = save_snapshot(
        db, snap.store_id, snap.business_date, payload,
        raw_inputs=raw_inputs, generated_by=current_user.id,
    )
    return {
        "id": new_snap.id,
        "version": new_snap.version,
        "business_date": new_snap.business_date.isoformat(),
    }


# ─────────────────────────────────────────
# 月報
# ─────────────────────────────────────────

def _aggregate_monthly(payloads: list[dict]) -> dict:
    """日報JSONリストから月報集計"""
    if not payloads:
        return {
            "ticket_count": 0,
            "guest_count": 0,
            "n_count": 0,
            "r_count": 0,
            "total_amount": 0,
            "extension_count": 0,
            "drink_s_total": 0,
            "drink_l_total": 0,
            "drink_mg_total": 0,
            "champagne_count": 0,
            "champagne_amount": 0,
            "set_count": 0,
            "alcohol_expense": 0,
            "other_expense": 0,
            "motivation": {},
            "hourly_arrivals": {},
            "course_counts": {},
            "cast_rotation_total": 0,
            "cast_rotation_per_cast": {},
            "base_pay_total": 0,
            "incentive_total": 0,
            "actual_pay_total": 0,
            "ratio_percent": None,
            "avg_per_guest": None,
            "avg_per_n": None,
            "avg_per_r": None,
            "drink_s_per_set": None,
            "drink_l_per_set": None,
            "drink_mg_per_set": None,
            "shot_cast_total": 0,
            "shot_cast_per_set": None,
            "champagne_count_per_set": None,
            "champagne_amount_per_set": None,
            "tissue_total": 0,
            "motivation_tissue": 0,
        }

    motivation = defaultdict(int)
    hourly = defaultdict(int)
    course = defaultdict(int)
    rotation_per_cast = defaultdict(int)
    custom_drinks_total: dict = defaultdict(int)
    # 略称 → ラベルマップ（最新の payload から取る）
    custom_drink_columns_latest: list = []

    sums = defaultdict(int)
    sum_n_amount = 0
    sum_r_amount = 0

    # キャスト別月次累積（cast_id があれば cast_id、無ければ "help:NAME"）
    cast_acc: dict = {}
    # 社員/アルバイト別月次累積（name でグルーピング）
    staff_acc: dict = {}

    def _cast_key(c: dict) -> str:
        cid = c.get("cast_id")
        if cid is not None:
            return f"id:{cid}"
        return f"help:{c.get('cast_name') or '?'}"

    for p in payloads:
        s = p.get("sales", {}) or {}
        cp = p.get("cast_payroll", {}) or {}
        for key in (
            "ticket_count", "guest_count", "n_count", "r_count",
            "total_amount", "extension_count",
            "drink_s_total", "drink_l_total", "drink_mg_total",
            "champagne_count", "champagne_amount",
            "set_count", "alcohol_expense", "other_expense",
            "cast_rotation_total",
        ):
            sums[key] += int(s.get(key) or 0)
        for k in ("base_pay_total", "incentive_total", "actual_pay_total"):
            sums[k] += int(cp.get(k) or 0)
        # 動機・時間帯・コース・キャスト別交代回数のマージ
        for k, v in (s.get("motivation") or {}).items():
            motivation[k] += int(v or 0)
        for k, v in (s.get("hourly_arrivals") or {}).items():
            hourly[k] += int(v or 0)
        for k, v in (s.get("course_counts") or {}).items():
            course[k] += int(v or 0)
        for k, v in (s.get("cast_rotation_per_cast") or {}).items():
            rotation_per_cast[k] += int(v or 0)
        # N/R 売上の按分は再計算が難しいので「avg_per_n × n_count」で逆算したいが、
        # ここでは「日報の avg_per_n × その日の n_count」を集計して総和を出す
        if s.get("avg_per_n") is not None and s.get("n_count"):
            sum_n_amount += int(s["avg_per_n"]) * int(s["n_count"])
        if s.get("avg_per_r") is not None and s.get("r_count"):
            sum_r_amount += int(s["avg_per_r"]) * int(s["r_count"])

        # custom_drink_columns（最後にロードしたものを採用）
        cdc = p.get("custom_drink_columns") or []
        if cdc:
            custom_drink_columns_latest = cdc
        # カスタムドリンク総数（伝票毎の custom_drinks を合算）
        for tb in (p.get("tickets") or []):
            for short, qty in (tb.get("custom_drinks") or {}).items():
                custom_drinks_total[short] += int(qty or 0)

        # キャスト別累積
        for c in (p.get("cast_attendance") or []):
            if c.get("is_absent"):
                continue
            key = _cast_key(c)
            if key not in cast_acc:
                cast_acc[key] = {
                    "cast_id": c.get("cast_id"),
                    "cast_name": c.get("cast_name"),
                    "is_help": bool(c.get("is_help")),
                    "work_days": 0,
                    "work_hours_total": 0.0,
                    "base_pay_total": 0,
                    "incentive_total": 0,
                    "daily_pay_total": 0,
                    "drink_s": 0,
                    "drink_l": 0,
                    "drink_mg": 0,
                    "shot_cast": 0,
                    "champagne_count": 0,
                    "champagne_amount": 0,
                    "perf_22_26_total": 0,
                    "n_tissue_count": 0,
                    "r_tissue_count": 0,
                    "closing_count": 0,
                    "tissue_count": 0,
                    "tissue_hours": 0.0,
                    "service_hours": 0.0,
                    "idle_hours": 0.0,
                    "custom_drinks": {},
                }
            acc = cast_acc[key]
            acc["work_days"] += 1
            acc["work_hours_total"] += float(c.get("work_hours") or 0)
            acc["base_pay_total"] += int(c.get("base_pay") or 0)
            acc["incentive_total"] += int(c.get("incentive_total") or 0)
            acc["daily_pay_total"] += int(c.get("daily_pay") or 0)
            acc["drink_s"] += int(c.get("drink_s") or 0)
            acc["drink_l"] += int(c.get("drink_l") or 0)
            acc["drink_mg"] += int(c.get("drink_mg") or 0)
            acc["shot_cast"] += int(c.get("shot_cast") or 0)
            acc["champagne_count"] += int(c.get("champagne_count") or 0)
            acc["champagne_amount"] += int(c.get("champagne_amount") or 0)
            acc["perf_22_26_total"] += int(c.get("perf_22_26") or 0)
            acc["n_tissue_count"] += int(c.get("n_tissue_count") or 0)
            acc["r_tissue_count"] += int(c.get("r_tissue_count") or 0)
            acc["closing_count"] += int(c.get("closing_count") or 0)
            acc["tissue_count"] += int(c.get("tissue_count") or 0)
            acc["tissue_hours"] += float(c.get("tissue_hours") or 0)
            acc["service_hours"] += float(c.get("service_hours") or 0)
            acc["idle_hours"] += float(c.get("idle_hours") or 0)
            for short, qty in (c.get("custom_drinks") or {}).items():
                acc["custom_drinks"][short] = acc["custom_drinks"].get(short, 0) + int(qty or 0)

        # 社員/アルバイト別累積
        for st in (p.get("staff_attendance") or []):
            if st.get("is_absent"):
                continue
            name = st.get("name") or "?"
            if name not in staff_acc:
                staff_acc[name] = {
                    "name": name,
                    "employee_type": st.get("employee_type"),
                    "work_days": 0,
                    "work_hours_total": 0.0,
                    "daily_pay_total": 0,
                }
            sa = staff_acc[name]
            sa["work_days"] += 1
            sa["work_hours_total"] += float(st.get("work_hours") or 0)
            sa["daily_pay_total"] += int(st.get("daily_pay") or 0)
            if not sa.get("employee_type") and st.get("employee_type"):
                sa["employee_type"] = st.get("employee_type")

    def _div(num, den):
        return int(num / den) if den else None

    ratio = None
    if sums["total_amount"] > 0:
        ratio = round(sums["actual_pay_total"] * 100 / sums["total_amount"], 1)

    # キャスト別累積を整形（時間は小数2桁）
    cast_summary = []
    for v in cast_acc.values():
        v["work_hours_total"] = round(v["work_hours_total"], 2)
        v["tissue_hours"] = round(v.get("tissue_hours", 0.0), 2)
        v["service_hours"] = round(v.get("service_hours", 0.0), 2)
        v["idle_hours"] = round(v.get("idle_hours", 0.0), 2)
        cast_summary.append(v)
    cast_summary.sort(key=lambda x: (x["is_help"], -(x["incentive_total"] or 0)))

    # 社員/アルバイト別累積を整形
    staff_summary = []
    for v in staff_acc.values():
        v["work_hours_total"] = round(v["work_hours_total"], 2)
        staff_summary.append(v)
    # 社員→アルバイト→その他、同区分内は時間降順
    _type_order = {"staff": 0, "part_time": 1}
    staff_summary.sort(key=lambda x: (_type_order.get(x.get("employee_type") or "", 9), -x["work_hours_total"]))

    # 月次利益率
    monthly_total_cost = 0
    daily_profit_rates = []
    for p in payloads:
        cb = p.get("cost_breakdown")
        if cb:
            monthly_total_cost += int(cb.get("total_cost") or 0)
        pr = p.get("profit_rate")
        if pr is not None:
            daily_profit_rates.append(pr)
    monthly_profit_rate = round(monthly_total_cost / sums["total_amount"] * 100, 1) if sums["total_amount"] > 0 else None

    # キャスト累積から派生する月次合計
    shot_cast_total = sum(int(c.get("shot_cast") or 0) for c in cast_summary)
    tissue_total = sum(int(c.get("tissue_count") or 0) for c in cast_summary)

    return {
        **sums,
        "motivation": dict(motivation),
        "hourly_arrivals": dict(hourly),
        "course_counts": dict(course),
        "cast_rotation_per_cast": dict(rotation_per_cast),
        "ratio_percent": ratio,
        "avg_per_guest": _div(sums["total_amount"], sums["guest_count"]),
        "avg_per_n": _div(sum_n_amount, sums["n_count"]),
        "avg_per_r": _div(sum_r_amount, sums["r_count"]),
        "drink_s_per_set": round(sums["drink_s_total"] / sums["set_count"], 2) if sums["set_count"] else None,
        "drink_l_per_set": round(sums["drink_l_total"] / sums["set_count"], 2) if sums["set_count"] else None,
        "drink_mg_per_set": round(sums["drink_mg_total"] / sums["set_count"], 2) if sums["set_count"] else None,
        "shot_cast_total": shot_cast_total,
        "shot_cast_per_set": round(shot_cast_total / sums["set_count"], 2) if sums["set_count"] else None,
        "champagne_count_per_set": round(sums["champagne_count"] / sums["set_count"], 2) if sums["set_count"] else None,
        "champagne_amount_per_set": round(sums["champagne_amount"] / sums["set_count"]) if sums["set_count"] else None,
        "tissue_total": tissue_total,
        "motivation_tissue": int((motivation or {}).get("ティッシュ", 0)),
        "cast_summary": cast_summary,
        "staff_summary": staff_summary,
        "custom_drinks_total": dict(custom_drinks_total),
        "custom_drink_columns": custom_drink_columns_latest,
        "profit_rate": monthly_profit_rate,
        "total_cost": monthly_total_cost,
    }


@router.get("/monthly")
def get_monthly(
    store_id: int = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """月報: 指定月の各日報スナップショット（最新版）を集計"""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month は 1-12")
    start = date_cls(year, month, 1)
    if month == 12:
        end = date_cls(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date_cls(year, month + 1, 1) - timedelta(days=1)

    rows = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date >= start,
        models.DailyReportSnapshot.business_date <= end,
    ).order_by(
        models.DailyReportSnapshot.business_date.asc(),
        models.DailyReportSnapshot.version.desc(),
    ).all()

    # 同じ日は最新版のみ
    by_date: dict = {}
    for r in rows:
        if r.business_date in by_date:
            continue
        by_date[r.business_date] = r

    payloads = [_enrich_legacy_payload(db, r.payload) for r in by_date.values() if r.payload]
    summary = _aggregate_monthly(payloads)

    return {
        "store_id": store_id,
        "year": year,
        "month": month,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "report_days": len(payloads),
        "summary": summary,
        "daily_breakdown": [
            {
                "business_date": d.isoformat(),
                "snapshot_id": by_date[d].id,
                "version": by_date[d].version,
                "total_amount": (by_date[d].payload or {}).get("sales", {}).get("total_amount", 0),
                "guest_count": (by_date[d].payload or {}).get("sales", {}).get("guest_count", 0),
            }
            for d in sorted(by_date.keys())
        ],
    }


# ─────────────────────────────────────────
# 月次ランキング（各指標の1位店舗）
# ─────────────────────────────────────────
_RANKING_METRICS = [
    ("total_amount", "売上", "yen"),
    ("guest_count", "客数", "num"),
    ("avg_per_guest", "客単価", "yen"),
    ("drink_l_total", "L数合計", "num"),
    ("drink_l_per_set", "1セットあたりL数", "num"),
    ("drink_mg_total", "MG数合計", "num"),
    ("drink_mg_per_set", "1セットあたりMG数", "num"),
    ("shot_cast_total", "ショット数合計", "num"),
    ("shot_cast_per_set", "1セットあたりショット数", "num"),
    ("champagne_count", "シャンパン本数合計", "num"),
    ("champagne_count_per_set", "1セットあたりシャンパン本数", "num"),
    ("champagne_amount", "シャンパン合計額", "yen"),
    ("champagne_amount_per_set", "1セットあたりシャンパン金額", "yen"),
    ("extension_count", "合計延長数", "num"),
    ("motivation_tissue", "来店動機ティッシュ数", "num"),
    ("tissue_total", "合計ティッシュ配布枚数", "num"),
    ("cast_rotation_total", "合計キャスト交代数", "num"),
]


def _compute_live_today_stats(db: Session, store_id: int) -> dict:
    """当日セッション中のライブ統計（月間ランキング用・当日分の加算値）"""
    session = db.query(models.BusinessSession).filter(
        models.BusinessSession.store_id == store_id,
        models.BusinessSession.is_closed == False,
    ).order_by(models.BusinessSession.opened_at.desc()).first()
    if session:
        since = session.opened_at
    else:
        now_jst = datetime.utcnow() + timedelta(hours=9)
        business_date = now_jst.date() - timedelta(days=1) if now_jst.hour < 12 else now_jst.date()
        since = datetime(business_date.year, business_date.month, business_date.day, 3, 0, 0)

    closed = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= since,
        models.Ticket.deleted_at.is_(None),
    ).all()
    opened = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == False,
        models.Ticket.deleted_at.is_(None),
        models.Ticket.started_at >= since,
    ).all()
    all_tickets = closed + opened

    def _grand(t):
        senkaikei = sum(
            abs(i.amount or 0) for i in (t.order_items or [])
            if i.canceled_at is None and (
                (i.item_name or '').startswith('先会計')
                or (i.item_name or '').startswith('分割清算')
                or (i.item_name or '').startswith('値引き')
            )
        )
        subtotal = (t.total_amount or 0) + senkaikei
        gross = round(subtotal * 1.21) - senkaikei
        return max(0, gross - (t.discount_amount or 0))

    total_amount = sum(_grand(t) for t in all_tickets)
    guest_count = sum(t.guest_count or 0 for t in all_tickets)
    extension_count = sum(t.extension_count or 0 for t in all_tickets)
    set_count = guest_count + extension_count

    drink_l = drink_mg = shot = champagne_count = champagne_amount = 0
    motivation_tissue_guests = 0
    for t in all_tickets:
        if (t.visit_motivation or '') == 'ティッシュ':
            motivation_tissue_guests += int(t.guest_count or 0)
        groups: dict = defaultdict(list)
        for o in (t.order_items or []):
            if o.canceled_at is not None:
                continue
            if o.item_type == 'drink_l':
                drink_l += int(o.quantity or 0)
            elif o.item_type == 'drink_mg':
                drink_mg += int(o.quantity or 0)
            elif o.item_type == 'shot_cast':
                shot += int(o.quantity or 0)
            elif o.item_type == 'champagne':
                groups[o.item_name or ''].append(o)
        for items in groups.values():
            champagne_count += 1
            for it in items:
                if (it.unit_price or 0) > 0:
                    champagne_amount += int(it.unit_price * (it.quantity or 0))

    # キャスト交代数（report_calc.rotation_count_for_ticket と同等のロジック）
    CAST_DRINK_TYPES = {'drink_s', 'drink_l', 'drink_mg', 'shot_cast', 'champagne', 'custom_menu'}
    rotation_total = 0
    for t in all_tickets:
        items = [
            o for o in (t.order_items or [])
            if o.cast_id is not None and o.canceled_at is None and o.item_type in CAST_DRINK_TYPES
        ]
        items.sort(key=lambda o: (o.created_at or datetime.min, o.id))
        for i in range(len(items) - 1):
            if items[i].cast_id != items[i + 1].cast_id:
                rotation_total += 1

    # ティッシュ配布枚数（当日 store の TissueDistribution 合算）
    tissue_total = 0
    for td in db.query(models.TissueDistribution).filter(
        models.TissueDistribution.store_id == store_id,
        models.TissueDistribution.started_at >= since,
    ).all():
        tissue_total += int(td.count or 0)

    return {
        "total_amount": total_amount,
        "guest_count": guest_count,
        "extension_count": extension_count,
        "set_count": set_count,
        "drink_l_total": drink_l,
        "drink_mg_total": drink_mg,
        "shot_cast_total": shot,
        "champagne_count": champagne_count,
        "champagne_amount": champagne_amount,
        "motivation_tissue": motivation_tissue_guests,
        "cast_rotation_total": rotation_total,
        "tissue_total": tissue_total,
    }


@router.get("/monthly-rankings")
def get_monthly_rankings(
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定月の各指標について1位の店舗を返す（当月の場合は当日ライブデータを加算）"""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month は 1-12")
    stores = db.query(models.Store).filter(models.Store.is_active == True).all()
    start = date_cls(year, month, 1)
    if month == 12:
        end = date_cls(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date_cls(year, month + 1, 1) - timedelta(days=1)
    today = (datetime.utcnow() + timedelta(hours=9)).date()
    is_current_month = (today.year == year and today.month == month)

    per_store: list[dict] = []
    for store in stores:
        rows = db.query(models.DailyReportSnapshot).filter(
            models.DailyReportSnapshot.store_id == store.id,
            models.DailyReportSnapshot.business_date >= start,
            models.DailyReportSnapshot.business_date <= end,
        ).order_by(
            models.DailyReportSnapshot.business_date.asc(),
            models.DailyReportSnapshot.version.desc(),
        ).all()
        by_date: dict = {}
        for r in rows:
            if r.business_date in by_date:
                continue
            by_date[r.business_date] = r
        payloads = [_enrich_legacy_payload(db, r.payload) for r in by_date.values() if r.payload]
        summary = dict(_aggregate_monthly(payloads))

        # 当月なら当日ライブデータを加算
        if is_current_month:
            live = _compute_live_today_stats(db, store.id)
            for k in ("total_amount", "guest_count", "extension_count",
                      "drink_l_total", "drink_mg_total", "shot_cast_total",
                      "champagne_count", "champagne_amount",
                      "motivation_tissue", "cast_rotation_total", "tissue_total"):
                summary[k] = (summary.get(k) or 0) + live.get(k, 0)
            live_set = live.get("set_count", 0)
            total_set = (summary.get("set_count") or 0) + live_set
            summary["set_count"] = total_set
            # per_set 系を再計算
            def _ps(num: float) -> Optional[float]:
                return round(num / total_set, 2) if total_set else None
            summary["drink_l_per_set"] = _ps(summary.get("drink_l_total") or 0)
            summary["drink_mg_per_set"] = _ps(summary.get("drink_mg_total") or 0)
            summary["shot_cast_per_set"] = _ps(summary.get("shot_cast_total") or 0)
            summary["champagne_count_per_set"] = _ps(summary.get("champagne_count") or 0)
            summary["champagne_amount_per_set"] = (
                round((summary.get("champagne_amount") or 0) / total_set) if total_set else None
            )
            # 客単価 再計算
            g = summary.get("guest_count") or 0
            summary["avg_per_guest"] = int((summary.get("total_amount") or 0) / g) if g else None

        per_store.append({
            "store_id": store.id,
            "store_name": store.name,
            "summary": summary,
        })

    rankings: dict = {}
    for key, label, fmt in _RANKING_METRICS:
        # 最大値と同値の店舗を全て拾う
        max_v = None
        for s in per_store:
            v = s["summary"].get(key)
            if v is None:
                continue
            if max_v is None or v > max_v:
                max_v = v
        tops: list = []
        if max_v is not None:
            for s in per_store:
                v = s["summary"].get(key)
                if v is not None and v == max_v:
                    tops.append({"store_id": s["store_id"], "store_name": s["store_name"], "value": v})
        rankings[key] = {"label": label, "format": fmt, "tops": tops}

    return {"year": year, "month": month, "rankings": rankings}
