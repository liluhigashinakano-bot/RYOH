"""顧客DBの preferences を確認"""
import sys, json
sys.path.insert(0, '.')
from app.database import SessionLocal
from app import models

db = SessionLocal()
customers = db.query(models.Customer).filter(models.Customer.is_active == True).all()
for c in customers:
    print(f"\n=== {c.name} ===")
    print(f"  total_visits={c.total_visits}, total_spend={c.total_spend}")
    print(f"  first_visit={c.first_visit_date}, last_visit={c.last_visit_date}")
    print(f"  preferences={json.dumps(c.preferences, ensure_ascii=False, indent=2)}")
db.close()
