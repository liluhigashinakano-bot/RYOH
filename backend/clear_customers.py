"""顧客テーブルを全削除"""
import sys
sys.path.insert(0, '.')
from app.database import SessionLocal
from app import models

db = SessionLocal()
count = db.query(models.Customer).delete()
db.commit()
db.close()
print(f"削除完了: {count}件")
