"""
Run this once to add new shipment detail columns to the existing database.
Usage: python migrate.py
"""
import sqlite3

conn = sqlite3.connect("shipments.db")
new_cols = [
    ("weight_kg",      "REAL    DEFAULT 0"),
    ("height_cm",      "REAL    DEFAULT 0"),
    ("width_cm",       "REAL    DEFAULT 0"),
    ("length_cm",      "REAL    DEFAULT 0"),
    ("description",    'TEXT    DEFAULT ""'),
    ("package_type",   'TEXT    DEFAULT ""'),
    ("image_filename", 'TEXT    DEFAULT ""'),
]
existing = [r[1] for r in conn.execute("PRAGMA table_info(shipments)").fetchall()]
for col, typedef in new_cols:
    if col not in existing:
        conn.execute(f"ALTER TABLE shipments ADD COLUMN {col} {typedef}")
        print(f"  ✓ Added column: {col}")
    else:
        print(f"  – Already exists: {col}")
conn.commit()
conn.close()
print("\nMigration complete.")
print("Columns:", [r[1] for r in sqlite3.connect("shipments.db").execute("PRAGMA table_info(shipments)").fetchall()])
