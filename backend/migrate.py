from app.database import engine
from sqlalchemy import text

columns = [
    # customers
    ("customers", "photo_path", "VARCHAR(500)"),
    ("customers", "age_group", "VARCHAR(10)"),
    ("customers", "features", "TEXT"),
    ("customers", "store_id", "INTEGER"),
    ("customers", "customer_code", "VARCHAR(20)"),
    ("customers", "merged_customer_ids", "TEXT"),
    ("customers", "merged_into_id", "INTEGER"),
    # casts
    ("casts", "cast_code", "VARCHAR(20)"),
    ("casts", "photo_path", "VARCHAR(500)"),
    ("casts", "birthday", "DATE"),
    ("casts", "employment_start_date", "DATE"),
    ("casts", "last_rate_change_date", "DATE"),
    # confirmed_shifts
    ("confirmed_shifts", "shift_data", "TEXT"),
    # tickets
    ("tickets", "guest_count", "INTEGER DEFAULT 1"),
    ("tickets", "plan_type", "VARCHAR(20)"),
    ("tickets", "visit_type", "VARCHAR(5)"),
]

with engine.connect() as conn:
    for table, col, col_type in columns:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            conn.commit()
            print(f"OK: {table}.{col} added")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print(f"OK: {table}.{col} already exists")
            else:
                print(f"ERROR ({table}.{col}):", e)

input("Press Enter to close...")
