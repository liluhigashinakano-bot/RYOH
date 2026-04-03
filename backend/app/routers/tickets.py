from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

CAST_DRINK_TYPES = {"drink_l", "drink_mg", "champagne"}


def _ticket_extra(ticket: models.Ticket) -> dict:
    """伝票の追加情報（キャスト名・E開始時刻・最終キャストドリンク時刻）を返す"""
    # 現在担当キャスト（ended_at が null の最新アサイン）
    current_cast_name = None
    e_started_at = None
    active_assignments = [a for a in (ticket.assignments or []) if a.ended_at is None]
    if active_assignments:
        latest = max(active_assignments, key=lambda a: a.started_at)
        current_cast_name = latest.cast.name if latest.cast else None
        e_started_at = latest.started_at

    # 最終キャストドリンク注文時刻
    last_drink_at = None
    drink_orders = [
        i for i in (ticket.order_items or [])
        if i.item_type in CAST_DRINK_TYPES and i.canceled_at is None
    ]
    if drink_orders:
        last_drink_at = max(i.created_at for i in drink_orders)

    # 顧客名
    customer_name = ticket.customer.name if ticket.customer else None

    return {
        "current_cast_name": current_cast_name,
        "e_started_at": e_started_at,
        "last_drink_at": last_drink_at,
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
    set_started_at: Optional[datetime] = None
    set_is_paused: bool = False
    set_paused_at: Optional[datetime] = None
    set_paused_seconds: int = 0
    # computed extras
    current_cast_name: Optional[str] = None
    e_started_at: Optional[datetime] = None
    last_drink_at: Optional[datetime] = None
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
        "set_started_at": ticket.set_started_at,
        "set_is_paused": ticket.set_is_paused or False,
        "set_paused_at": ticket.set_paused_at,
        "set_paused_seconds": ticket.set_paused_seconds or 0,
        **extra,
    }
    return data


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
        if i.canceled_at is None
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
    return [_to_response(t) for t in tickets]


@router.post("", response_model=TicketResponse)
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    store = db.query(models.Store).filter(models.Store.id == data.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")

    ticket = models.Ticket(
        store_id=data.store_id,
        customer_id=data.customer_id,
        table_no=data.table_no,
        staff_id=current_user.id,
        notes=data.notes,
        guest_count=data.guest_count,
        plan_type=data.plan_type,
        visit_type=data.visit_type,
    )
    if store.set_price and store.set_price > 0:
        ticket.total_amount = store.set_price

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    if store.set_price and store.set_price > 0:
        item = models.OrderItem(
            ticket_id=ticket.id,
            item_type="set",
            item_name="セット料金",
            quantity=1,
            unit_price=store.set_price,
            amount=store.set_price,
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
    ticket.total_amount += amount

    if data.item_type == "extension":
        ticket.extension_count += 1

    db.commit()
    return {"message": "注文を追加しました", "id": item.id, "total_amount": ticket.total_amount}


@router.delete("/orders/{item_id}")
def cancel_order(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
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

    db.commit()
    return {"message": "注文をキャンセルしました"}


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


@router.get("/live/{store_id}")
def get_live_summary(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from datetime import date
    today = date.today()

    open_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == False,
    ).all()

    closed_today = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= datetime.combine(today, datetime.min.time()),
    ).all()

    return {
        "open_count": len(open_tickets),
        "open_amount": sum(t.total_amount for t in open_tickets),
        "closed_count": len(closed_today),
        "closed_amount": sum(t.total_amount for t in closed_today),
        "total_amount": sum(t.total_amount for t in open_tickets) + sum(t.total_amount for t in closed_today),
        "open_tickets": [{"id": t.id, "table_no": t.table_no, "amount": t.total_amount, "started_at": t.started_at} for t in open_tickets],
    }
