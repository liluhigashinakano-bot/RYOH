from app.database import engine
from sqlalchemy import text

columns = [
    ("photo_path", "VARCHAR(500)"),
    ("age_group", "VARCHAR(10)"),
    ("features", "TEXT"),
]

with engine.connect() as conn:
    for col, col_type in columns:
        try:
            conn.execute(text(f"ALTER TABLE customers ADD COLUMN {col} {col_type}"))
            conn.commit()
            print(f"OK: {col} added")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print(f"OK: {col} already exists")
            else:
                print(f"ERROR ({col}):", e)

input("Press Enter to close...")
