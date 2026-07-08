"""
Initialize the SQLite database with schema and a default admin account.
Run once: python init_db.py
"""
import sqlite3
from werkzeug.security import generate_password_hash

DB = "shipments.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    email         TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK(role IN ('admin','client'))
);

CREATE TABLE IF NOT EXISTS shipments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_number     TEXT    NOT NULL UNIQUE,
    client_id           INTEGER NOT NULL REFERENCES users(id),
    current_status      TEXT    NOT NULL DEFAULT 'Pending',
    destination_address TEXT    NOT NULL DEFAULT '',
    weight_kg           REAL    DEFAULT 0,
    height_cm           REAL    DEFAULT 0,
    width_cm            REAL    DEFAULT 0,
    length_cm           REAL    DEFAULT 0,
    description         TEXT    DEFAULT '',
    package_type        TEXT    DEFAULT '',
    image_filename      TEXT    DEFAULT '',
    created_at          DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shipment_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id  INTEGER NOT NULL REFERENCES shipments(id),
    city_name    TEXT    NOT NULL,
    status_notes TEXT    NOT NULL,
    updated_at   DATETIME DEFAULT (datetime('now'))
);
"""

def init():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    # Default admin account
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, 'admin')",
            ("admin", generate_password_hash("admin123"), "admin@shiptrack.com")
        )
        conn.commit()
        print("✓ Database initialized. Admin → username: admin / password: admin123")
    except sqlite3.IntegrityError:
        print("✓ Database already initialized.")
    conn.close()

if __name__ == "__main__":
    init()
