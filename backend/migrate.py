from app.database import engine
from sqlalchemy import text

columns = [
    # customers
    ("customers", "photo_path", "VARCHAR(500)"),
    ("customers", "age_group", "VARCHAR(10)"),
    ("customers", "features", "TEXT"),
    ("customers", "store_id", "INTEGER"),
    # casts
    ("casts", "photo_path", "VARCHAR(500)"),
    ("casts", "birthday", "DATE"),
    ("casts", "employment_start_date", "DATE"),
    ("casts", "last_rate_change_date", "DATE"),
    # confirmed_shifts
    ("confirmed_shifts", "shift_data", "TEXT"),
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
