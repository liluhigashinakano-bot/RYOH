from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from ..database import get_db
from .. import models
from ..auth import get_current_user
from ..services.incentive import (
    build_incentive_map,
    build_custom_menu_label_map,
    calc_incentive_snapshot,
)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _to_bar_time(utc_dt: Optional[datetime]) -> str:
    """UTC datetime をバー時間表記(JST, 深夜は24:xx)に変換"""
    if not utc_dt:
        return "?"
    jst = utc_dt + timedelta(hours=9)
    h = jst.hour
    if h < 6:
        h += 24
    return f"{h}:{jst.strftime('%M')}"

CAST_DRINK_TYPES = {"drink_s", "drink_l", "drink_mg", "champagne", "custom_menu"}


def _ticket_extra(ticket: models.Ticket) -> dict:
    """伝票の追加情報（キャスト名・E開始時刻・最終キャストドリンク時刻）を返す"""
    # 接客中キャスト（CastAssignment の ended_at が null の active 全部）
    current_casts: list = []
    e_started_at = None
    active_assignments = [a for a in (ticket.assignments or []) if a.ended_at is None]
    if active_assignments:
        sorted_active = sorted(active_assignments, key=lambda a: a.started_at)
        for a in sorted_active:
            if a.cast and a.cast_id is not None:
                current_casts.append({"cast_id": a.cast_id, "cast_name": a.cast.stage_name})
        latest = sorted_active[-1]
        e_started_at = latest.started_at

    # 推しキャスト（担当）= Ticket.featured_cast_id
    featured_cast_name = None
    if ticket.featured_cast_id is not None and ticket.featured_cast:
        featured_cast_name = ticket.featured_cast.stage_name
    # 後方互換: current_cast_name は推しキャスト名（既存表示用）
    current_cast_name = featured_cast_name

    # ドリンクタイマーの最終注文時刻
    # 仕様:
    # - シャンパン以外は1キャストにつき最新の1件だけ表示（古い品目は消える）
    # - シャンパンは品目別にすべて表示（複数並ぶ）
    # 構造: { "drink_l": [{...}], ..., "champagne": [...], ... }
    drink_clears = getattr(ticket, 'drink_clears', None) or {}
    last_drink_times: dict = {dt: [] for dt in CAST_DRINK_TYPES}

    # 1キャストの最新ドリンク（シャンパン以外）を求める
    latest_per_cast: dict = {}  # cid -> {drink_type, cast_name, last_at, item_name}
    for item in (ticket.order_items or []):
        if item.canceled_at is not None or item.cast_id is None:
            continue
        if item.item_type not in CAST_DRINK_TYPES or item.item_type == "champagne":
            continue
        cid = item.cast_id
        last_at_iso = item.created_at.isoformat() if item.created_at else None
        if last_at_iso is None:
            continue
        cur = latest_per_cast.get(cid)
        if cur is None or last_at_iso > cur["last_at"]:
            latest_per_cast[cid] = {
                "drink_type": item.item_type,
                "cast_id": cid,
                "cast_name": item.cast.stage_name if item.cast else f"Cast{cid}",
                "last_at": last_at_iso,
                "item_name": item.item_name,
            }

    for entry in latest_per_cast.values():
        clear_key = f"{entry['cast_id']}_{entry['drink_type']}"
        cleared_at_iso = drink_clears.get(clear_key)
        if cleared_at_iso:
            try:
                cleared_at = datetime.fromisoformat(cleared_at_iso)
            except Exception:
                cleared_at = None
            if cleared_at and cleared_at.isoformat() >= entry["last_at"]:
                continue
        last_drink_times[entry["drink_type"]].append({
            "cast_id": entry["cast_id"],
            "cast_name": entry["cast_name"],
            "last_at": entry["last_at"],
            "item_name": entry["item_name"],
        })

    # シャンパンは従来通り（item_name 別、cast_id 別に並べる）
    champ_map: dict = {}  # (cid, item_name) -> entry
    for item in (ticket.order_items or []):
        if item.canceled_at is not None or item.cast_id is None or item.item_type != "champagne":
            continue
        last_at_iso = item.created_at.isoformat() if item.created_at else None
        if last_at_iso is None:
            continue
        key = (item.cast_id, item.item_name or "")
        cur = champ_map.get(key)
        if cur is None or last_at_iso > cur["last_at"]:
            champ_map[key] = {
                "cast_id": item.cast_id,
                "cast_name": item.cast.stage_name if item.cast else f"Cast{item.cast_id}",
                "last_at": last_at_iso,
                "item_name": item.item_name,
            }
    for entry in champ_map.values():
        clear_key = f"{entry['cast_id']}_champagne"
        cleared_at_iso = drink_clears.get(clear_key)
        if cleared_at_iso:
            try:
                cleared_at = datetime.fromisoformat(cleared_at_iso)
            except Exception:
                cleared_at = None
            if cleared_at and cleared_at.isoformat() >= entry["last_at"]:
                continue
        last_drink_times["champagne"].append(entry)

    # 顧客名
    customer_name = ticket.customer.name if ticket.customer else None

    return {
        "current_cast_name": current_cast_name,
        "featured_cast_id": ticket.featured_cast_id,
        "featured_cast_name": featured_cast_name,
        "current_casts": current_casts,
        "e_started_at": e_started_at,
        "last_drink_times": last_drink_times,
        "customer_name": customer_name,
    }


class TicketCreate(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    table_no: Optional[str] = None
    notes: Optional[str] = None
    guest_count: int = 1
    n_count: Optional[int] = None  # 指定なしなら visit_type から自動算出
    r_count: Optional[int] = None
    plan_type: Optional[str] = None
    visit_type: Optional[str] = None
    visit_motivation: Optional[str] = None
    motivation_cast_id: Optional[int] = None
    motivation_note: Optional[str] = None


class CastDistributionEntry(BaseModel):
    cast_id: int
    ratio: int  # 0-100


class OrderItemCreate(BaseModel):
    item_type: str
    item_name: Optional[str] = None
    quantity: int = 1
    unit_price: int
    cast_id: Optional[int] = None
    # シャンパン等で複数キャストに分配する場合のみ指定
    cast_distribution: Optional[List[CastDistributionEntry]] = None
    # 延長 (extension) のロック用：何期目の延長か（0始まり）。
    # 同じ ticket × period_no が既に登録済みなら no-op。
    period_no: Optional[int] = None


class TicketClose(BaseModel):
    payment_method: models.PaymentMethod
    cash_amount: int = 0
    card_amount: int = 0
    code_amount: int = 0
    discount_amount: int = 0


class OrderItemResponse(BaseModel):
    id: int
    item_type: str
    item_name: Optional[str]
    quantity: int
    unit_price: int
    amount: int
    cast_id: Optional[int]
    canceled_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TicketResponse(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int]
    table_no: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    is_closed: bool
    set_count: int
    extension_count: int
    total_amount: int
    discount_amount: int
    notes: Optional[str]
    guest_count: int = 1
    plan_type: Optional[str] = None
    visit_type: Optional[str] = None
    visit_motivation: Optional[str] = None
    motivation_cast_id: Optional[int] = None
    motivation_cast_name: Optional[str] = None
    motivation_note: Optional[str] = None
    set_started_at: Optional[datetime] = None
    set_is_paused: bool = False
    set_paused_at: Optional[datetime] = None
    set_paused_seconds: int = 0
    # computed extras
    current_cast_name: Optional[str] = None
    featured_cast_id: Optional[int] = None
    featured_cast_name: Optional[str] = None
    current_casts: Optional[List[dict]] = None
    e_started_at: Optional[datetime] = None
    last_drink_times: Optional[dict] = None
    customer_name: Optional[str] = None

    class Config:
        from_attributes = True


class TicketDetailResponse(TicketResponse):
    order_items: list[OrderItemResponse] = []


def _to_response(ticket: models.Ticket) -> dict:
    extra = _ticket_extra(ticket)
    data = {
        "id": ticket.id,
        "store_id": ticket.store_id,
        "customer_id": ticket.customer_id,
        "table_no": ticket.table_no,
        "started_at": ticket.started_at,
        "ended_at": ticket.ended_at,
        "is_closed": ticket.is_closed,
        "set_count": ticket.set_count,
        "extension_count": ticket.extension_count,
        "total_amount": ticket.total_amount,
        "discount_amount": ticket.discount_amount,
        "notes": ticket.notes,
        "guest_count": ticket.guest_count or 1,
        "n_count": ticket.n_count or 0,
        "r_count": ticket.r_count or 0,
        "plan_type": ticket.plan_type,
        "visit_type": ticket.visit_type,
        "visit_motivation": ticket.visit_motivation,
        "motivation_cast_id": ticket.motivation_cast_id,
        "motivation_note": ticket.motivation_note,
        "set_started_at": ticket.set_started_at,
        "set_is_paused": ticket.set_is_paused or False,
        "set_paused_at": ticket.set_paused_at,
        "set_paused_seconds": ticket.set_paused_seconds or 0,
        "current_cast_name": extra["current_cast_name"],
        "featured_cast_id": extra["featured_cast_id"],
        "featured_cast_name": extra["featured_cast_name"],
        "current_casts": extra["current_casts"],
        "e_started_at": extra["e_started_at"],
        "last_drink_times": extra["last_drink_times"],
        "customer_name": extra["customer_name"],
        "motivation_cast_name": ticket.motivation_cast.stage_name if getattr(ticket, 'motivation_cast', None) else None,
        "payment_method": ticket.payment_method.value if ticket.payment_method else None,
        "cash_amount": ticket.cash_amount or 0,
        "card_amount": ticket.card_amount or 0,
        "code_amount": ticket.code_amount or 0,
    }
    return data


@router.get("/logs")
def get_order_logs(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """店舗の注文削除・変更履歴を返す（直近200件）"""
    logs = (
        db.query(models.OrderItemLog)
        .join(models.Ticket, models.OrderItemLog.ticket_id == models.Ticket.id)
        .filter(models.Ticket.store_id == store_id)
        .order_by(models.OrderItemLog.changed_at.desc())
        .limit(200)
        .all()
    )
    result = []
    for log in logs:
        ticket = log.ticket
        result.append({
            "id": log.id,
            "changed_at": log.changed_at,
            "action": log.action,
            "ticket_id": log.ticket_id,
            "table_no": ticket.table_no if ticket else None,
            "item_name": log.item_name or log.item_type,
            "old_quantity": log.old_quantity,
            "new_quantity": log.new_quantity,
            "old_amount": log.old_amount,
            "new_amount": log.new_amount,
            "operator_name": log.operator_name,
            "reason": log.reason,
            "changed_by_name": log.changed_by_user.name if log.changed_by_user else None,
        })
    return result


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    data = _to_response(ticket)
    data["order_items"] = [
        OrderItemResponse.model_validate(i)
        for i in ticket.order_items
    ]
    return data


@router.get("")
def get_tickets(
    store_id: int,
    is_closed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.deleted_at.is_(None),
    )
    if is_closed is not None:
        query = query.filter(models.Ticket.is_closed == is_closed)
    tickets = query.order_by(models.Ticket.started_at.desc()).all()
    # オープン中は display_order ASC → 卓番号自然順
    if is_closed is False:
        import re
        def _sort_key(t):
            order = t.display_order if t.display_order is not None else 10**9
            tn = t.table_no or ''
            m = re.match(r'^([A-Za-z]*)(\d*)$', tn)
            if m:
                return (order, m.group(1), int(m.group(2)) if m.group(2) else 0, tn)
            return (order, tn, 0, tn)
        tickets.sort(key=_sort_key)
    result = []
    for t in tickets:
        data = _to_response(t)
        data["order_items"] = [
            {"id": i.id, "item_type": i.item_type, "item_name": i.item_name or i.item_type, "quantity": i.quantity, "unit_price": i.unit_price, "amount": i.amount,
             "created_at": i.created_at.isoformat() if i.created_at else None}
            for i in t.order_items if i.canceled_at is None
        ]
        result.append(data)
    return result


@router.post("", response_model=TicketResponse)
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    store = db.query(models.Store).filter(models.Store.id == data.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")

    # プラン別セット料金（1人あたり）
    SET_PRICES = {"premium": 3500, "standard": 2500}
    unit_set_price = SET_PRICES.get(data.plan_type or "standard", 2500)
    guest_count = data.guest_count or 1
    total_set = unit_set_price * guest_count

    # n_count/r_count: 明示指定優先・無ければ visit_type から自動算出
    if data.n_count is not None or data.r_count is not None:
        n_count = data.n_count or 0
        r_count = data.r_count or 0
    elif data.visit_type == "N":
        n_count, r_count = guest_count, 0
    elif data.visit_type == "R":
        n_count, r_count = 0, guest_count
    else:
        n_count, r_count = 0, 0

    ticket = models.Ticket(
        store_id=data.store_id,
        customer_id=data.customer_id,
        table_no=data.table_no,
        staff_id=current_user.id,
        notes=data.notes,
        guest_count=guest_count,
        n_count=n_count,
        r_count=r_count,
        plan_type=data.plan_type,
        visit_type=data.visit_type,
        visit_motivation=data.visit_motivation,
        motivation_cast_id=data.motivation_cast_id,
        motivation_note=data.motivation_note,
        total_amount=total_set,
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # セット料金を人数分まとめて1件追加
    item = models.OrderItem(
        ticket_id=ticket.id,
        item_type="set",
        item_name="セット料金",
        quantity=guest_count,
        unit_price=unit_set_price,
        amount=total_set,
    )
    db.add(item)
    db.commit()

    return _to_response(ticket)


@router.post("/{ticket_id}/set-start")
def set_start(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id, models.Ticket.is_closed == False
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    if ticket.set_started_at:
        raise HTTPException(status_code=400, detail="既にスタート済みです")
    ticket.set_started_at = datetime.utcnow()
    ticket.set_is_paused = False
    ticket.set_paused_seconds = 0
    db.commit()
    return {"message": "セットスタート"}


@router.post("/{ticket_id}/set-toggle")
def set_toggle(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id, models.Ticket.is_closed == False
    ).first()
    if not ticket or not ticket.set_started_at:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    now = datetime.utcnow()
    if ticket.set_is_paused:
        # 再開: 一時停止時間を累積
        if ticket.set_paused_at:
            paused_sec = int((now - ticket.set_paused_at).total_seconds())
            ticket.set_paused_seconds = (ticket.set_paused_seconds or 0) + paused_sec
        ticket.set_is_paused = False
        ticket.set_paused_at = None
    else:
        # 一時停止
        ticket.set_is_paused = True
        ticket.set_paused_at = now

    db.commit()
    return {"message": "トグル完了", "is_paused": ticket.set_is_paused}


@router.post("/{ticket_id}/orders")
def add_order(
    ticket_id: int,
    data: OrderItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    amount = data.quantity * data.unit_price

    # 通常延長 (合流ではない) は period_no で重複防止
    is_normal_ext = (
        data.item_type == "extension"
        and data.cast_id is None
        and not (data.item_name or '').startswith('合流')
    )
    if is_normal_ext and data.period_no is not None:
        # 同じ ticket × period_no が存在すれば no-op（削除済みも含む。
        # 手動で削除した延長をAutoExtenderが再追加しないようにするため）
        existing = db.query(models.OrderItem).filter(
            models.OrderItem.ticket_id == ticket_id,
            models.OrderItem.item_type == "extension",
            models.OrderItem.cast_id.is_(None),
            models.OrderItem.period_no == data.period_no,
        ).first()
        if existing is not None:
            return {
                "message": "既に登録済み",
                "id": existing.id,
                "total_amount": ticket.total_amount,
                "skipped": True,
            }
        # 新規行を作成（quantity = ゲスト数）
        guest = max(1, ticket.guest_count or 1)
        new_item = models.OrderItem(
            ticket_id=ticket_id,
            item_type="extension",
            item_name=data.item_name,
            quantity=guest,
            unit_price=data.unit_price,
            amount=data.unit_price * guest,
            cast_id=None,
            period_no=data.period_no,
        )
        db.add(new_item)
        ticket.total_amount += data.unit_price * guest
        ticket.extension_count = (ticket.extension_count or 0) + 1  # 期数のみ
        db.commit()
        return {"message": "延長を追加しました", "id": new_item.id, "total_amount": ticket.total_amount}

    # インセンティブスナップショット & 分配情報の計算
    snapshot = None
    distribution_json = None
    # シャンパンなど cast_distribution で複数キャストに分配する場合、cast_id は None。
    # その場合も snapshot は計算する必要がある（バック額の元データになるため）。
    if data.cast_id is not None or data.cast_distribution:
        imap = build_incentive_map(db, ticket.store_id)
        lmap = build_custom_menu_label_map(db, ticket.store_id)
        snapshot = calc_incentive_snapshot(
            data.item_type, data.item_name, data.unit_price, data.quantity, imap, lmap
        )
    if data.cast_distribution:
        distribution_json = [
            {"cast_id": e.cast_id, "ratio": e.ratio} for e in data.cast_distribution
        ]

    # キャスト指定ドリンク注文時はそのキャストの配り中を終了
    if data.cast_id is not None:
        from .tissue import end_active_tissue_for_cast
        end_active_tissue_for_cast(db, data.cast_id)

    # 常に新規レコードを作成（個別タイムスタンプ保持のため）
    item = models.OrderItem(
        ticket_id=ticket_id,
        item_type=data.item_type,
        item_name=data.item_name,
        quantity=data.quantity,
        unit_price=data.unit_price,
        amount=amount,
        cast_id=data.cast_id,
        incentive_snapshot=snapshot,
        cast_distribution=distribution_json,
    )
    db.add(item)
    item_id = None

    ticket.total_amount += amount

    if data.item_type == "extension":
        ticket.extension_count += 1

    db.commit()
    return {"message": "注文を追加しました", "id": item_id, "total_amount": ticket.total_amount}


class OrderItemUpdate(BaseModel):
    quantity: int
    operator_name: Optional[str] = None
    reason: Optional[str] = None


class OrderItemCancel(BaseModel):
    operator_name: Optional[str] = None
    reason: Optional[str] = None


@router.patch("/orders/{item_id}")
def update_order(
    item_id: int,
    data: OrderItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="数量は1以上にしてください")
    item = db.query(models.OrderItem).filter(
        models.OrderItem.id == item_id,
        models.OrderItem.canceled_at == None
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="注文が見つかりません")
    ticket = db.query(models.Ticket).filter(models.Ticket.id == item.ticket_id).first()
    old_quantity = item.quantity
    old_amount = item.amount
    item.quantity = data.quantity
    item.amount = item.unit_price * data.quantity
    ticket.total_amount += item.amount - old_amount

    # キャスト選択ありドリンクの数量増加 = 追加注文相当 → タイマーをリセット
    if (
        item.cast_id is not None
        and item.item_type in CAST_DRINK_TYPES
        and data.quantity > old_quantity
    ):
        item.created_at = datetime.utcnow()
        # drink_clears の該当キーを消す（新規注文があった扱い）
        try:
            dc = dict(ticket.drink_clears or {})
            ck = f"{item.cast_id}_{item.item_type}"
            if ck in dc:
                del dc[ck]
                ticket.drink_clears = dc
        except Exception:
            pass

    # インセンティブスナップショットを再計算（数量変更に追従）
    if item.cast_id is not None:
        imap = build_incentive_map(db, ticket.store_id)
        lmap = build_custom_menu_label_map(db, ticket.store_id)
        new_snap = calc_incentive_snapshot(
            item.item_type, item.item_name, item.unit_price or 0, data.quantity, imap, lmap
        )
        if new_snap is not None:
            item.incentive_snapshot = new_snap
    # 履歴記録
    log = models.OrderItemLog(
        ticket_id=item.ticket_id,
        order_item_id=item.id,
        action='update_quantity',
        item_type=item.item_type,
        item_name=item.item_name,
        old_quantity=old_quantity,
        new_quantity=data.quantity,
        old_amount=old_amount,
        new_amount=item.amount,
        changed_by=current_user.id,
        operator_name=data.operator_name,
        reason=data.reason,
    )
    db.add(log)
    db.commit()
    return {"ok": True, "total_amount": ticket.total_amount}


@router.delete("/orders/{item_id}")
def cancel_order(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _do_cancel(item_id, None, None, db, current_user)


@router.post("/orders/{item_id}/cancel")
def cancel_order_with_operator(
    item_id: int,
    data: OrderItemCancel,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _do_cancel(item_id, data.operator_name, data.reason, db, current_user)


def _do_cancel(item_id: int, operator_name: Optional[str], reason: Optional[str], db, current_user):
    item = db.query(models.OrderItem).filter(
        models.OrderItem.id == item_id,
        models.OrderItem.canceled_at == None
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="注文が見つかりません")

    ticket = db.query(models.Ticket).filter(models.Ticket.id == item.ticket_id).first()
    item.canceled_at = datetime.utcnow()
    item.canceled_by = current_user.id
    ticket.total_amount -= item.amount
    if item.item_type == "extension" and ticket.extension_count > 0:
        ticket.extension_count -= 1
    # 履歴記録
    log = models.OrderItemLog(
        ticket_id=item.ticket_id,
        order_item_id=item.id,
        action='cancel',
        item_type=item.item_type,
        item_name=item.item_name,
        old_quantity=item.quantity,
        new_quantity=0,
        old_amount=item.amount,
        new_amount=0,
        changed_by=current_user.id,
        operator_name=operator_name,
        reason=reason,
    )
    db.add(log)
    db.commit()
    return {"message": "注文をキャンセルしました"}


class DrinkClearRequest(BaseModel):
    cast_id: int
    drink_type: str


@router.post("/{ticket_id}/drink-clear")
def drink_clear(
    ticket_id: int,
    data: DrinkClearRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    clears = dict(getattr(ticket, 'drink_clears', None) or {})
    clear_key = f"{data.cast_id}_{data.drink_type}"
    clears[clear_key] = datetime.utcnow().isoformat()
    ticket.drink_clears = clears
    db.commit()
    return {"ok": True}


class SetCustomerRequest(BaseModel):
    customer_id: Optional[int] = None


@router.post("/{ticket_id}/set-customer", response_model=TicketResponse)
def set_customer(
    ticket_id: int,
    data: SetCustomerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    ticket.customer_id = data.customer_id
    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


class SetCastRequest(BaseModel):
    cast_id: Optional[int] = None
    assignment_type: str = "jounai"


@router.post("/{ticket_id}/set-cast", response_model=TicketResponse)
def set_cast(
    ticket_id: int,
    data: SetCastRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """担当（推しキャスト）を1人だけ設定する。
    CastAssignment は触らない（あちらは「接客中」用）。"""
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    ticket.featured_cast_id = data.cast_id  # None で解除
    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


class SetAssignmentsRequest(BaseModel):
    cast_ids: List[int]
    assignment_type: str = "jounai"


@router.post("/{ticket_id}/assignments/set", response_model=TicketResponse)
def set_assignments(
    ticket_id: int,
    data: SetAssignmentsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """付け回しを一括設定する。
    - その卓の現在 active な assignments を全て ended_at にする
    - 各 cast_id について、他の卓で active なら ended_at にして移動
    - 配り中の active があれば終了
    - 新規 active 行を追加
    """
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    now = datetime.utcnow()
    new_cast_ids = list(dict.fromkeys(data.cast_ids))  # 重複除去・順序保持

    # 1. この卓の現在 active を全て終了
    for a in (ticket.assignments or []):
        if a.ended_at is None:
            a.ended_at = now

    if new_cast_ids:
        # 2. 他の卓で active なものを終了（移動）
        other_active = db.query(models.CastAssignment).filter(
            models.CastAssignment.cast_id.in_(new_cast_ids),
            models.CastAssignment.ended_at.is_(None),
            models.CastAssignment.ticket_id != ticket_id,
        ).all()
        for a in other_active:
            a.ended_at = now

        # 2.5 配り中(active)を終了（接客中設定で配り中から外す）
        from .tissue import end_active_tissue_for_cast
        for cid in new_cast_ids:
            end_active_tissue_for_cast(db, cid)

        # 3. 新規 active を追加
        for cid in new_cast_ids:
            db.add(models.CastAssignment(
                ticket_id=ticket_id,
                cast_id=cid,
                assignment_type=data.assignment_type,
                started_at=now,
            ))

    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


class ReorderRequest(BaseModel):
    store_id: int
    ordered_ids: List[int]


@router.post("/reorder")
def reorder_tickets(
    data: ReorderRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ドラッグ後の伝票並び順を保存"""
    rows = db.query(models.Ticket).filter(
        models.Ticket.id.in_(data.ordered_ids),
        models.Ticket.store_id == data.store_id,
    ).all()
    by_id = {r.id: r for r in rows}
    for idx, tid in enumerate(data.ordered_ids):
        t = by_id.get(tid)
        if t is not None:
            t.display_order = idx
    db.commit()
    return {"ok": True}


class TicketDeleteRequest(BaseModel):
    operator_name: str
    reason: Optional[str] = None


@router.post("/{ticket_id}/delete")
def delete_ticket(
    ticket_id: int,
    data: TicketDeleteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """伝票を論理削除（deleted_at セット）。
    変更履歴に「ticket_delete」アクションを記録。"""
    if not data.operator_name or not data.operator_name.strip():
        raise HTTPException(status_code=400, detail="担当者名は必須です")
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    if ticket.deleted_at is not None:
        raise HTTPException(status_code=400, detail="既に削除されています")
    ticket.deleted_at = datetime.utcnow()
    ticket.deleted_by = current_user.id
    log = models.OrderItemLog(
        ticket_id=ticket_id,
        order_item_id=None,
        action='ticket_delete',
        item_type=None,
        item_name=f"伝票削除 (卓 {ticket.table_no or '-'} / 合計 ¥{ticket.total_amount or 0})",
        changed_by=current_user.id,
        operator_name=data.operator_name,
        reason=data.reason,
    )
    db.add(log)
    db.commit()
    return {"ok": True}


class GroupReduceRequest(BaseModel):
    item_type: str
    item_name: Optional[str] = None
    unit_price: int
    target_quantity: int
    operator_name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/{ticket_id}/reduce-group")
def reduce_group(
    ticket_id: int,
    data: GroupReduceRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """グループ化された注文の合計数量を削減する（超過分を最新順にキャンセル）"""
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    # 対象グループの未キャンセルアイテムを古い順に取得
    group_items = [
        i for i in (ticket.order_items or [])
        if i.canceled_at is None
        and i.item_type == data.item_type
        and (i.item_name or '') == (data.item_name or '')
        and i.unit_price == data.unit_price
    ]
    group_items.sort(key=lambda i: i.created_at or datetime.min, reverse=True)  # 最新順

    current_total = sum(i.quantity for i in group_items)
    to_cancel = current_total - data.target_quantity

    if to_cancel <= 0:
        raise HTTPException(status_code=400, detail="現在の数量以上には増やせません")

    now = datetime.utcnow()
    canceled_count = 0
    for item in group_items:
        if to_cancel <= 0:
            break
        if item.quantity <= to_cancel:
            # まるごとキャンセル
            item.canceled_at = now
            item.canceled_by = current_user.id
            ticket.total_amount -= item.amount
            if item.item_type == "extension" and ticket.extension_count > 0:
                ticket.extension_count -= item.quantity
            log = models.OrderItemLog(
                ticket_id=ticket_id,
                order_item_id=item.id,
                action='cancel',
                item_type=item.item_type,
                item_name=item.item_name,
                old_quantity=item.quantity,
                new_quantity=0,
                old_amount=item.amount,
                new_amount=0,
                changed_by=current_user.id,
                operator_name=data.operator_name,
                reason=data.reason,
            )
            db.add(log)
            to_cancel -= item.quantity
            canceled_count += item.quantity
        else:
            # 一部削減
            old_qty = item.quantity
            old_amt = item.amount
            item.quantity -= to_cancel
            item.amount = item.unit_price * item.quantity
            ticket.total_amount -= (old_amt - item.amount)
            if item.item_type == "extension":
                ticket.extension_count = max(0, ticket.extension_count - to_cancel)
            log = models.OrderItemLog(
                ticket_id=ticket_id,
                order_item_id=item.id,
                action='update_quantity',
                item_type=item.item_type,
                item_name=item.item_name,
                old_quantity=old_qty,
                new_quantity=item.quantity,
                old_amount=old_amt,
                new_amount=item.amount,
                changed_by=current_user.id,
                operator_name=data.operator_name,
                reason=data.reason,
            )
            db.add(log)
            to_cancel = 0

    db.commit()
    db.refresh(ticket)
    resp = _to_response(ticket)
    resp["order_items"] = [OrderItemResponse.model_validate(i) for i in ticket.order_items]
    return resp


class ChampagneRatioUpdate(BaseModel):
    old_item_name: str
    new_item_name: str
    operator_name: Optional[str] = None
    reason: Optional[str] = None
    # 新形式: cast_distribution を渡せば item_name 文字列に依存せず構造的に更新
    cast_distribution: Optional[List[CastDistributionEntry]] = None


@router.patch("/{ticket_id}/update-champagne")
def update_champagne_ratios(
    ticket_id: int,
    data: ChampagneRatioUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """シャンパンのキャスト配分率を一括更新（item_nameを書き換え）。
    クローズ済み伝票でも編集可能。日報スナップショットがあれば自動再生成する。"""
    items = db.query(models.OrderItem).filter(
        models.OrderItem.ticket_id == ticket_id,
        models.OrderItem.item_name == data.old_item_name,
        models.OrderItem.item_type == 'champagne',
        models.OrderItem.canceled_at == None,
    ).all()
    if not items:
        raise HTTPException(status_code=404, detail="シャンパン注文が見つかりません")

    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()

    # cast_distribution は必須（item_name 文字列だけの更新は許可しない）
    if not data.cast_distribution:
        raise HTTPException(status_code=400, detail="cast_distribution が必要です")

    # ratio バリデーション
    total = sum(e.ratio for e in data.cast_distribution)
    if total != 100:
        raise HTTPException(status_code=400, detail=f"分配率の合計は100%必須です（現在 {total}%）")
    if any(e.ratio < 0 for e in data.cast_distribution):
        raise HTTPException(status_code=400, detail="分配率は 0 以上にしてください")
    # キャスト存在チェック
    cast_ids = list({e.cast_id for e in data.cast_distribution})
    casts = db.query(models.Cast).filter(
        models.Cast.id.in_(cast_ids),
        models.Cast.store_id == ticket.store_id,
    ).all() if ticket else []
    if len(casts) != len(cast_ids):
        raise HTTPException(status_code=400, detail="無効なキャストIDが含まれています")

    # 新形式: cast_distribution が指定されていればそれを全行に適用
    distribution_json = None
    if data.cast_distribution:
        distribution_json = [
            {"cast_id": e.cast_id, "ratio": e.ratio} for e in data.cast_distribution
        ]

    # 旧分配の表示（変更ログ用）
    old_holder = next((i for i in items if isinstance(i.cast_distribution, list) and i.cast_distribution), None)
    old_dist = old_holder.cast_distribution if old_holder else []

    def _fmt(dist) -> str:
        if not dist:
            return "(なし)"
        ids = [d.get("cast_id") if isinstance(d, dict) else d.cast_id for d in dist]
        name_map = {
            c.id: c.stage_name
            for c in db.query(models.Cast).filter(models.Cast.id.in_(ids)).all()
        }
        parts = []
        for d in dist:
            cid = d.get("cast_id") if isinstance(d, dict) else d.cast_id
            ratio = d.get("ratio") if isinstance(d, dict) else d.ratio
            parts.append(f"{name_map.get(cid, f'#{cid}')}={ratio}%")
        return ", ".join(parts)

    change_summary = f"{_fmt(old_dist)} → {_fmt(data.cast_distribution or [])}"
    log_reason = (change_summary + (f" / 理由: {data.reason}" if data.reason else ""))[:200]

    # ログは代表行（最初の1行）に1件だけ記録
    log = models.OrderItemLog(
        ticket_id=ticket_id,
        order_item_id=items[0].id,
        action='update_ratio',
        item_type='champagne',
        item_name=data.new_item_name,
        old_quantity=items[0].quantity,
        new_quantity=items[0].quantity,
        old_amount=items[0].amount,
        new_amount=items[0].amount,
        changed_by=current_user.id,
        operator_name=data.operator_name,
        reason=log_reason,
    )
    db.add(log)

    for item in items:
        item.item_name = data.new_item_name
        if distribution_json is not None:
            item.cast_distribution = distribution_json

    db.commit()

    # 該当日の日報スナップショットを更新
    if ticket and distribution_json is not None:
        try:
            from datetime import timedelta as _td
            from ..services.report_builder import (
                get_latest_snapshot, regenerate_from_snapshot, save_snapshot,
            )
            ref = ticket.ended_at or ticket.started_at
            if ref is not None:
                biz_date = (ref + _td(hours=9)).date()
                snap = get_latest_snapshot(db, ticket.store_id, biz_date)
                if snap and snap.raw_inputs:
                    # raw_inputs があれば完全再生成
                    payload, raw_inputs = regenerate_from_snapshot(
                        db, snap, generated_by=current_user.id
                    )
                    save_snapshot(
                        db, snap.store_id, snap.business_date, payload,
                        raw_inputs=raw_inputs, generated_by=current_user.id,
                    )
                elif snap:
                    # raw_inputs 無し → シャンパン額・本数のみ強制再計算して payload を上書き保存
                    from .reports import _enrich_legacy_payload
                    new_payload = _enrich_legacy_payload(db, snap.payload, force=True)
                    snap.payload = new_payload
                    db.commit()
        except Exception as e:
            print(f"[WARNING] 日報更新失敗: {e}")

    return {"ok": True, "total_amount": ticket.total_amount if ticket else None}


class TicketPatch(BaseModel):
    started_at: Optional[datetime] = None
    guest_count: Optional[int] = None
    n_count: Optional[int] = None
    r_count: Optional[int] = None
    table_no: Optional[str] = None
    visit_type: Optional[str] = None
    plan_type: Optional[str] = None
    visit_motivation: Optional[str] = None
    motivation_cast_id: Optional[int] = None
    update_header: bool = False   # True のとき table_no/visit_type/plan_type を null でも更新する
    operator_name: Optional[str] = None
    reason: Optional[str] = None


@router.patch("/{ticket_id}", response_model=TicketResponse)
def patch_ticket(
    ticket_id: int,
    data: TicketPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    if data.started_at is not None:
        new_started_at = data.started_at.replace(tzinfo=None)
        old_started_at = ticket.started_at
        ticket.started_at = new_started_at
        # セット開始時刻も同期
        ticket.set_started_at = new_started_at
        # 変更ログ記録（order_item_id は不要なので0で代用）
        # order_item_idはNullableでないためダミー的に扱う。先に flush して ticket.id を確定
        time_log = models.OrderItemLog(
            ticket_id=ticket_id,
            order_item_id=None,
            action='change_start_time',
            item_name=f"入店時間変更: {_to_bar_time(old_started_at)} → {_to_bar_time(new_started_at)}",
            changed_by=current_user.id,
            operator_name=data.operator_name,
            reason=data.reason,
        )
        db.add(time_log)

        # 現在時刻から経過した延長期数を再計算 (新仕様: extension_count = 期数のみ)
        now_utc = datetime.utcnow()
        elapsed_seconds = max(0, (now_utc - new_started_at).total_seconds())
        guest_count = ticket.guest_count or 1
        ext_price = 4000 if ticket.plan_type == 'premium' else 3000
        new_period_count = int(elapsed_seconds // (40 * 60))
        old_period_count = ticket.extension_count or 0
        diff = new_period_count - old_period_count  # 期数の差

        if diff > 0:
            # 不足期分を1行ずつ追加（quantity = ゲスト数）
            for _ in range(diff):
                item = models.OrderItem(
                    ticket_id=ticket_id,
                    item_type='extension',
                    unit_price=ext_price,
                    quantity=guest_count,
                    amount=ext_price * guest_count,
                )
                db.add(item)
                ticket.total_amount += ext_price * guest_count
            ticket.extension_count = new_period_count
        elif diff < 0:
            # 超過期分をキャンセル（新しい順に）
            ext_items = [
                i for i in (ticket.order_items or [])
                if i.item_type == 'extension' and i.canceled_at is None
            ]
            cancel_count = min(abs(diff), len(ext_items))
            for item in ext_items[-cancel_count:]:
                item.canceled_at = datetime.utcnow()
                ticket.total_amount = max(0, ticket.total_amount - item.amount)
            ticket.extension_count = new_period_count

    if data.guest_count is not None:
        new_guest_count = max(1, data.guest_count)
        ticket.guest_count = new_guest_count

    # n_count / r_count の更新（明示指定のみ反映、合計が guest_count を超えないよう調整）
    if data.n_count is not None or data.r_count is not None:
        new_n = max(0, data.n_count if data.n_count is not None else (ticket.n_count or 0))
        new_r = max(0, data.r_count if data.r_count is not None else (ticket.r_count or 0))
        gc = ticket.guest_count or 1
        # 合計が gc を超える場合は r 側を切り詰め
        if new_n + new_r > gc:
            new_r = max(0, gc - new_n)
        ticket.n_count = new_n
        ticket.r_count = new_r

    if data.visit_motivation is not None or data.update_header:
        new_motivation = data.visit_motivation or None
        if new_motivation != ticket.visit_motivation:
            ticket.visit_motivation = new_motivation
            ticket.motivation_cast_id = data.motivation_cast_id if new_motivation else None

    if data.table_no is not None or data.update_header:
        new_table_no = data.table_no or ticket.table_no
        if new_table_no != ticket.table_no:
            old_val = ticket.table_no or ''
            ticket.table_no = new_table_no
            log = models.OrderItemLog(
                ticket_id=ticket_id,
                order_item_id=None,
                action='change_table_no',
                item_name=f"卓番変更: {old_val} → {new_table_no}",
                changed_by=current_user.id,
                operator_name=data.operator_name,
                reason=data.reason,
            )
            db.add(log)

    if data.visit_type is not None or data.update_header:
        new_visit_type = data.visit_type or None
        if new_visit_type != ticket.visit_type:
            old_val = ticket.visit_type or ''
            ticket.visit_type = new_visit_type
            log = models.OrderItemLog(
                ticket_id=ticket_id,
                order_item_id=None,
                action='change_visit_type',
                item_name=f"来店種別変更: {old_val} → {new_visit_type or '未設定'}",
                changed_by=current_user.id,
                operator_name=data.operator_name,
                reason=data.reason,
            )
            db.add(log)
            # 旧UIから visit_type だけ更新された場合、n_count/r_count も同期
            # （n_count/r_count が明示指定された場合は上の分岐で既に上書きされている）
            if data.n_count is None and data.r_count is None:
                gc = ticket.guest_count or 1
                if new_visit_type == "N":
                    ticket.n_count, ticket.r_count = gc, 0
                elif new_visit_type == "R":
                    ticket.n_count, ticket.r_count = 0, gc

    if data.plan_type is not None or data.update_header:
        new_plan_type = data.plan_type if data.plan_type is not None else (ticket.plan_type or 'standard')
        if new_plan_type != (ticket.plan_type or 'standard'):
            old_val = ticket.plan_type or 'standard'
            ticket.plan_type = new_plan_type
            log = models.OrderItemLog(
                ticket_id=ticket_id,
                order_item_id=None,
                action='change_plan_type',
                item_name=f"プラン変更: {old_val} → {new_plan_type}",
                changed_by=current_user.id,
                operator_name=data.operator_name,
                reason=data.reason,
            )
            db.add(log)

    # セット料金の自動更新（guest_count または plan_type が変わった場合）
    if data.update_header and (data.guest_count is not None or data.plan_type is not None):
        final_guest = ticket.guest_count or 1
        final_plan = ticket.plan_type or 'standard'
        SET_PRICES = {'premium': 3500, 'standard': 2500}
        new_unit = SET_PRICES.get(final_plan, 2500)
        new_total = new_unit * final_guest
        set_item = next(
            (i for i in (ticket.order_items or [])
             if i.item_type == 'set' and i.item_name == 'セット料金' and i.canceled_at is None),
            None
        )
        if set_item:
            old_total = set_item.amount
            set_item.quantity = final_guest
            set_item.unit_price = new_unit
            set_item.amount = new_total
            ticket.total_amount += (new_total - old_total)

    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


@router.post("/{ticket_id}/close", response_model=TicketResponse)
def close_ticket(
    ticket_id: int,
    data: TicketClose,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    ticket.is_closed = True
    ticket.ended_at = datetime.utcnow()
    ticket.payment_method = data.payment_method
    ticket.cash_amount = data.cash_amount
    ticket.card_amount = data.card_amount
    ticket.code_amount = data.code_amount
    ticket.discount_amount = data.discount_amount
    ticket.total_amount = max(0, ticket.total_amount - data.discount_amount)

    if ticket.customer_id:
        customer = db.query(models.Customer).filter(models.Customer.id == ticket.customer_id).first()
        if customer:
            customer.total_visits += 1
            customer.total_spend += ticket.total_amount
            customer.ltv = customer.total_spend
            from datetime import date
            customer.last_visit_date = date.today()
            if not customer.first_visit_date:
                customer.first_visit_date = date.today()

    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


class JoinRequest(BaseModel):
    guest_count: int = 1
    n_count: Optional[int] = None             # 指定なしなら visit_type から自動算出
    r_count: Optional[int] = None
    visit_type: Optional[str] = None          # N / R
    customer_name: Optional[str] = None
    visit_motivation: Optional[str] = None
    motivation_cast_id: Optional[int] = None
    motivation_note: Optional[str] = None
    plan_type: str = "standard"               # standard / premium


@router.post("/{ticket_id}/join", response_model=TicketResponse)
def join_ticket(
    ticket_id: int,
    data: JoinRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    SET_PRICES = {"premium": 3500, "standard": 2500}
    unit_price = SET_PRICES.get(data.plan_type, 2500)
    amount = unit_price * data.guest_count

    # 表示名を組み立て
    parts = [f"{data.guest_count}名様合流"]
    if data.visit_type:
        parts.append(data.visit_type)
    if data.customer_name:
        parts.append(data.customer_name)
    if data.visit_motivation:
        m = data.visit_motivation
        if data.motivation_note:
            m += f"/{data.motivation_note}"
        parts.append(m)
    parts.append("プレミアム" if data.plan_type == "premium" else "スタンダード")
    item_name = "・".join(parts)

    item = models.OrderItem(
        ticket_id=ticket_id,
        item_type="join",
        item_name=item_name,
        quantity=data.guest_count,
        unit_price=unit_price,
        amount=amount,
    )
    db.add(item)
    ticket.total_amount += amount
    ticket.guest_count = (ticket.guest_count or 1) + data.guest_count

    # n_count/r_count の加算
    if data.n_count is not None or data.r_count is not None:
        add_n = data.n_count or 0
        add_r = data.r_count or 0
    elif data.visit_type == "N":
        add_n, add_r = data.guest_count, 0
    elif data.visit_type == "R":
        add_n, add_r = 0, data.guest_count
    else:
        add_n, add_r = 0, 0
    ticket.n_count = (ticket.n_count or 0) + add_n
    ticket.r_count = (ticket.r_count or 0) + add_r

    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


class MergeRequest(BaseModel):
    target_ticket_id: int   # 合算先伝票ID


@router.post("/{ticket_id}/merge", response_model=TicketResponse)
def merge_ticket(
    ticket_id: int,
    data: MergeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ticket_id の注文を target_ticket_id へ移して ticket_id を閉じる"""
    if ticket_id == data.target_ticket_id:
        raise HTTPException(status_code=400, detail="同じ伝票には合算できません")

    source = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False,
    ).first()
    target = db.query(models.Ticket).filter(
        models.Ticket.id == data.target_ticket_id,
        models.Ticket.is_closed == False,
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="元伝票が見つかりません")
    if not target:
        raise HTTPException(status_code=404, detail="合算先伝票が見つかりません")

    # source の未キャンセル注文を target へ移す
    active_items = [i for i in (source.order_items or []) if i.canceled_at is None]
    for item in active_items:
        item.ticket_id = data.target_ticket_id
        target.total_amount += item.amount
        if item.item_type == "extension":
            target.extension_count += 1

    target.guest_count = (target.guest_count or 1) + (source.guest_count or 1)
    target.n_count = (target.n_count or 0) + (source.n_count or 0)
    target.r_count = (target.r_count or 0) + (source.r_count or 0)

    # source を閉じる（合算済みとして 0 円）
    source.is_closed = True
    source.ended_at = datetime.utcnow()
    source.payment_method = models.PaymentMethod.cash
    source.total_amount = 0
    source.notes = (source.notes or "") + f" [合算→{data.target_ticket_id}]"

    db.commit()
    db.refresh(target)
    return _to_response(target)


class WarikanPayment(BaseModel):
    amount: int
    method: str  # cash / card / code


class WarikanRequest(BaseModel):
    payments: List[WarikanPayment]


@router.post("/{ticket_id}/warikan", response_model=TicketDetailResponse)
def warikan_ticket(
    ticket_id: int,
    data: WarikanRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """割り勘: 複数の分割清算を一括・アトミックに登録する"""
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    METHOD_LABELS = {"cash": "現金", "card": "カード決済", "code": "コード決済"}
    cash_paid = 0
    card_paid = 0
    code_paid = 0
    for p in data.payments:
        if p.amount <= 0:
            continue
        method_label = METHOD_LABELS.get(p.method, p.method)
        item = models.OrderItem(
            ticket_id=ticket_id,
            item_type="other",
            item_name=f"分割清算（{method_label}）",
            quantity=1,
            unit_price=-p.amount,
            amount=-p.amount,
        )
        db.add(item)
        ticket.total_amount -= p.amount
        if p.method == "cash":
            cash_paid += p.amount
        elif p.method == "card":
            card_paid += p.amount
        elif p.method == "code":
            code_paid += p.amount

    db.flush()

    # 合計が0になったら自動的に会計済みにする
    if _calc_grand_total(ticket) <= 0:
        ticket.is_closed = True
        ticket.ended_at = datetime.utcnow()
        ticket.cash_amount = (ticket.cash_amount or 0) + cash_paid
        ticket.card_amount = (ticket.card_amount or 0) + card_paid
        ticket.code_amount = (ticket.code_amount or 0) + code_paid
        methods_used = [m for m, v in [("cash", cash_paid), ("card", card_paid), ("code", code_paid)] if v > 0]
        if len(methods_used) == 1:
            ticket.payment_method = models.PaymentMethod(methods_used[0])
        elif len(methods_used) > 1:
            ticket.payment_method = models.PaymentMethod.mixed

        # 顧客統計更新
        if ticket.customer_id:
            from sqlalchemy.orm import Session as OrmSession
            customer = db.query(models.Customer).filter(models.Customer.id == ticket.customer_id).first()
            if customer:
                from datetime import date
                customer.total_visits = (customer.total_visits or 0) + 1
                customer.total_spend = (customer.total_spend or 0) + ticket.total_amount
                customer.ltv = customer.total_spend
                customer.last_visit_date = date.today()
                if not customer.first_visit_date:
                    customer.first_visit_date = date.today()

    db.commit()
    db.refresh(ticket)
    resp = _to_response(ticket)
    resp["order_items"] = [
        OrderItemResponse.model_validate(i)
        for i in ticket.order_items
    ]
    return resp


def _calc_grand_total(ticket: models.Ticket) -> int:
    """チケットのgrandTotal（税サ込み・値引き・先会計反映後）を計算"""
    sk = sum(
        abs(i.amount) for i in (ticket.order_items or [])
        if i.item_name and (
            i.item_name.startswith('先会計') or
            i.item_name.startswith('分割清算') or
            i.item_name.startswith('値引き')
        ) and not i.canceled_at
    )
    sub = ticket.total_amount + sk
    return round(sub * 1.21) - sk


@router.get("/live/{store_id}")
def get_live_summary(
    store_id: int,
    session_opened_at: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from datetime import date, timedelta
    # 営業日: JST で 12時未満は前日扱い
    now_jst = datetime.utcnow() + timedelta(hours=9)
    if now_jst.hour < 12:
        business_date = now_jst.date() - timedelta(days=1)
    else:
        business_date = now_jst.date()
    # 当日12時(JST)=当日03時(UTC) から翌日12時(JST) まで
    day_start_utc = datetime(business_date.year, business_date.month, business_date.day, 3, 0, 0)
    day_end_utc = day_start_utc + timedelta(hours=24)

    # セッション開始時刻が指定されている場合はそれ以降に絞る（同日複数セッション対策）
    if session_opened_at:
        try:
            since = datetime.fromisoformat(session_opened_at.replace('Z', '+00:00')).replace(tzinfo=None)
            day_start_utc = max(day_start_utc, since)
        except Exception:
            pass

    open_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == False,
        models.Ticket.deleted_at.is_(None),
        models.Ticket.started_at >= day_start_utc,
    ).all()

    closed_today = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == True,
        models.Ticket.deleted_at.is_(None),
        models.Ticket.ended_at >= day_start_utc,
        models.Ticket.ended_at < day_end_utc,
    ).all()

    closed_grand = sum(_calc_grand_total(t) for t in closed_today)
    open_grand = sum(_calc_grand_total(t) for t in open_tickets)

    # 支払い方法別集計（cash_amount / card_amount は ticket に記録済み）
    cash_tickets   = [t for t in closed_today if t.payment_method and t.payment_method.value in ('cash', 'mixed')]
    card_tickets   = [t for t in closed_today if t.payment_method and t.payment_method.value in ('card', 'mixed')]
    code_tickets   = [t for t in closed_today if t.payment_method and t.payment_method.value == 'code']

    def ticket_cash(t):
        return t.cash_amount or 0
    def ticket_card(t):
        return t.card_amount or 0
    def ticket_grand(t):
        return _calc_grand_total(t)

    # 現金売上 = 現金支払い分の合計
    cash_sales = sum(ticket_cash(t) for t in cash_tickets)
    # カード/コード伝票（先会計・割り勘を含む全決済）
    card_closed = [
        {"id": t.id, "table_no": t.table_no, "grand_total": _calc_grand_total(t),
         "card_amount": t.card_amount or 0, "payment_method": t.payment_method.value if t.payment_method else None,
         "ended_at": t.ended_at.isoformat() if t.ended_at else None}
        for t in closed_today if (t.card_amount or 0) > 0
    ]
    code_closed = [
        {"id": t.id, "table_no": t.table_no, "grand_total": _calc_grand_total(t),
         "code_amount": _calc_grand_total(t), "payment_method": t.payment_method.value if t.payment_method else None,
         "ended_at": t.ended_at.isoformat() if t.ended_at else None}
        for t in closed_today if t.payment_method and t.payment_method.value == 'code'
    ]

    return {
        "open_count": len(open_tickets),
        "open_amount": open_grand,
        "closed_count": len(closed_today),
        "closed_amount": closed_grand,
        "total_amount": open_grand + closed_grand,
        "cash_sales": cash_sales,
        "card_sales": sum(t["card_amount"] for t in card_closed),
        "code_sales": sum(t["code_amount"] for t in code_closed),
        "card_tickets": card_closed,
        "code_tickets": code_closed,
        "open_tickets": [{"id": t.id, "table_no": t.table_no, "amount": _calc_grand_total(t), "started_at": t.started_at} for t in open_tickets],
    }
