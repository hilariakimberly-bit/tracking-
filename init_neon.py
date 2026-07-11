import psycopg2
from werkzeug.security import generate_password_hash

DB_URL = "postgresql://neondb_owner:npg_0nLAsdXy6Nqu@ep-red-breeze-atwzp1qa.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require"

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        username      TEXT   NOT NULL UNIQUE,
        password_hash TEXT   NOT NULL,
        email         TEXT   NOT NULL,
        role          TEXT   NOT NULL CHECK(role IN ('admin','client'))
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS shipments (
        id                  SERIAL PRIMARY KEY,
        tracking_number     TEXT   NOT NULL UNIQUE,
        client_id           INT    NOT NULL REFERENCES users(id),
        current_status      TEXT   NOT NULL DEFAULT 'Pending',
        destination_address TEXT   NOT NULL DEFAULT '',
        weight_kg           REAL   DEFAULT 0,
        height_cm           REAL   DEFAULT 0,
        width_cm            REAL   DEFAULT 0,
        length_cm           REAL   DEFAULT 0,
        description         TEXT   DEFAULT '',
        package_type        TEXT   DEFAULT '',
        image_filename      TEXT   DEFAULT '',
        created_at          TIMESTAMP DEFAULT NOW()
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS shipment_history (
        id           SERIAL PRIMARY KEY,
        shipment_id  INT  NOT NULL REFERENCES shipments(id),
        city_name    TEXT NOT NULL,
        status_notes TEXT NOT NULL,
        updated_at   TIMESTAMP DEFAULT NOW()
    )
""")

cur.execute("SELECT id FROM users WHERE username = 'admin'")
if not cur.fetchone():
    cur.execute(
        "INSERT INTO users (username, password_hash, email, role) VALUES (%s, %s, %s, 'admin')",
        ("admin", generate_password_hash("admin123"), "admin@logisticsroyal.com")
    )
    print("Admin user created.")
else:
    print("Admin user already exists.")

conn.commit()
conn.close()
print("Database initialized successfully!")
