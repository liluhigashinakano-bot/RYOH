from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

CAST_DRINK_TYPES = {"drink_s", "drink_l", "drink_mg", "champagne"}


def _ticket_extra(ticket: models.Ticket) -> dict:
    """伝票の追加情報（キャスト名・E開始時刻・最終キャストドリンク時刻）を返す"""
    # 現在担当キャスト（ended_at が null の最新アサイン）
    current_cast_name = None
    e_started_at = None
    active_assignments = [a for a in (ticket.assignments or []) if a.ended_at is None]
    if active_assignments:
        latest = max(active_assignments, key=lambda a: a.started_at)
        current_cast_name = latest.cast.stage_name if latest.cast else None
        e_started_at = latest.started_at

    # 種別×キャストごとの最終注文時刻
    # 構造: { "drink_l": [{"cast_id": 1, "cast_name": "すずな", "last_at": datetime}, ...], ... }
    drink_clears = getattr(ticket, 'drink_clears', None) or {}
    last_drink_times: dict = {}
    for drink_type in CAST_DRINK_TYPES:
        orders = [
            i for i in (ticket.order_items or [])
            if i.item_type == drink_type and i.canceled_at is None and i.cast_id is not None
        ]
        if not orders:
            last_drink_times[drink_type] = []
            continue
        # キャストIDごとにグループ化して最終時刻を取得
        cast_map_local: dict = {}
        for item in orders:
            cid = item.cast_id
            if cid not in cast_map_local or item.created_at > cast_map_local[cid]["last_at"]:
                cast_name = item.cast.stage_name if item.cast else f"Cast{cid}"
                cast_map_local[cid] = {"cast_id": cid, "cast_name": cast_name, "last_at": item.created_at}
        # クリア済み（cleared_at >= last_at）のキャストを除外
        result = []
        for entry in cast_map_local.values():
            clear_key = f"{entry['cast_id']}_{drink_type}"
            cleared_at_iso = drink_clears.get(clear_key)
            if cleared_at_iso:
                try:
                    cleared_at = datetime.fromisoformat(cleared_at_iso)
                except Exception:
                    cleared_at = None
                if cleared_at and cleared_at >= entry["last_at"]:
                    continue  # クリア済みのためスキップ
            result.append(entry)
        last_drink_times[drink_type] = result

    # 顧客名
    customer_name = ticket.customer.name if ticket.customer else None

    return {
        "current_cast_name": current_cast_name,
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
    plan_type: Optional[str] = None
    visit_type: Optional[str] = None
    visit_motivation: Optional[str] = None
    motivation_cast_id: Optional[int] = None
    motivation_note: Optional[str] = None


class OrderItemCreate(BaseModel):
    item_type: str
    item_name: Optional[str] = None
    quantity: int = 1
    unit_price: int
    cast_id: Optional[int] = None


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
    query = db.query(models.Ticket).filter(models.Ticket.store_id == store_id)
    if is_closed is not None:
        query = query.filter(models.Ticket.is_closed == is_closed)
    tickets = query.order_by(models.Ticket.started_at.desc()).all()
    result = []
    for t in tickets:
        data = _to_response(t)
        data["order_items"] = [
            {"id": i.id, "item_name": i.item_name or i.item_type, "quantity": i.quantity, "unit_price": i.unit_price, "amount": i.amount,
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

    ticket = models.Ticket(
        store_id=data.store_id,
        customer_id=data.customer_id,
        table_no=data.table_no,
        staff_id=current_user.id,
        notes=data.notes,
        guest_count=guest_count,
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

    # 同じ品目（item_type・item_name・unit_price・cast_id）が未キャンセルで存在すれば数量を加算
    # setは個別行として管理するため統合しない
    existing = None
    if data.item_type != 'set':
        existing = next((
            i for i in (ticket.order_items or [])
            if i.canceled_at is None
            and i.item_type == data.item_type
            and (i.item_name or '') == (data.item_name or '')
            and i.unit_price == data.unit_price
            and i.cast_id == data.cast_id
        ), None)

    if existing:
        existing.quantity += data.quantity
        existing.amount += amount
        existing.created_at = datetime.utcnow()  # D時間リセット
        item_id = existing.id
    else:
        item = models.OrderItem(
            ticket_id=ticket_id,
            item_type=data.item_type,
            item_name=data.item_name,
            quantity=data.quantity,
            unit_price=data.unit_price,
            amount=amount,
            cast_id=data.cast_id,
        )
        db.add(item)
        item_id = None  # commit後に取得

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
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    now = datetime.utcnow()
    # 既存アクティブアサインを終了
    for a in (ticket.assignments or []):
        if a.ended_at is None:
            a.ended_at = now
    if data.cast_id:
        new_assignment = models.CastAssignment(
            ticket_id=ticket_id,
            cast_id=data.cast_id,
            assignment_type=data.assignment_type,
            started_at=now,
        )
        db.add(new_assignment)
    db.commit()
    db.refresh(ticket)
    return _to_response(ticket)


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


class TicketPatch(BaseModel):
    started_at: Optional[datetime] = None
    guest_count: Optional[int] = None
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
            order_item_id=0,
            action='change_start_time',
            item_name=f"入店時間変更: {old_started_at.strftime('%H:%M') if old_started_at else '?'} → {new_started_at.strftime('%H:%M')}",
            changed_by=current_user.id,
            operator_name=data.operator_name,
            reason=data.reason,
        )
        db.add(time_log)

        # 現在時刻から経過した延長回数を再計算
        # extension_count はゲスト数×延長期数で管理（AutoExtenderがゲスト数分リクエストするため）
        now_utc = datetime.utcnow()
        elapsed_seconds = max(0, (now_utc - new_started_at).total_seconds())
        guest_count = ticket.guest_count or 1
        ext_price = 4000 if ticket.plan_type == 'premium' else 3000
        new_period_count = int(elapsed_seconds // (40 * 60))
        new_ext_count = new_period_count * guest_count  # ゲスト数込みの合計
        old_ext_count = ticket.extension_count or 0
        diff = new_ext_count - old_ext_count  # 追加/削除すべき注文件数

        if diff > 0:
            # 不足分の延長注文を追加
            for _ in range(diff):
                item = models.OrderItem(
                    ticket_id=ticket_id,
                    item_type='extension',
                    unit_price=ext_price,
                    quantity=1,
                    amount=ext_price,
                )
                db.add(item)
                ticket.total_amount += ext_price
            ticket.extension_count = new_ext_count
        elif diff < 0:
            # 超過分の延長注文をキャンセル（新しい順に）
            ext_items = [
                i for i in (ticket.order_items or [])
                if i.item_type == 'extension' and i.canceled_at is None
            ]
            cancel_count = min(abs(diff), len(ext_items))
            for item in ext_items[-cancel_count:]:
                item.canceled_at = datetime.utcnow()
                ticket.total_amount = max(0, ticket.total_amount - item.amount)
            ticket.extension_count = new_ext_count

    if data.guest_count is not None:
        new_guest_count = max(1, data.guest_count)
        ticket.guest_count = new_guest_count

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
    ).all()

    closed_today = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == True,
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
