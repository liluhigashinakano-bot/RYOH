"""最新営業のシャンパン注文の incentive_snapshot/cast_distribution を確認"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.app.database import SessionLocal
from backend.app import models
import json

db = SessionLocal()
items = db.query(models.OrderItem).filter(
    models.OrderItem.item_type == "champagne",
    models.OrderItem.canceled_at.is_(None),
).order_by(models.OrderItem.id.desc()).limit(15).all()

for i in items:
    print(f"id={i.id} ticket={i.ticket_id} name={i.item_name} unit_price={i.unit_price} qty={i.quantity} cast_id={i.cast_id}")
    print(f"  snapshot: {json.dumps(i.incentive_snapshot, ensure_ascii=False) if i.incentive_snapshot else None}")
    print(f"  distribution: {json.dumps(i.cast_distribution, ensure_ascii=False) if i.cast_distribution else None}")
db.close()
