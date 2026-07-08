"""
Logistics Royal - Shipment Tracking Application
PostgreSQL version for Vercel deployment
"""
import os
import uuid
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "logistics-royal-dev-secret")

UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXT   = {"png", "jpg", "jpeg", "webp", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Email config ──────────────────────────────────────────────────────────────
try:
    import email_config
except ImportError:
    class email_config:
        MAIL_ENABLED  = os.environ.get("MAIL_ENABLED", "false").lower() == "true"
        MAIL_SENDER   = os.environ.get("MAIL_SENDER", "")
        MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
        MAIL_SMTP     = os.environ.get("MAIL_SMTP", "smtp.hostinger.com")
        MAIL_PORT     = int(os.environ.get("MAIL_PORT", "465"))


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        return psycopg2.connect(
            db_url,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    # ── Local fallback: SQLite ──
    import sqlite3
    conn = sqlite3.connect("shipments.db")
    conn.row_factory = sqlite3.Row
    return conn

def query(sql, args=(), one=False, commit=False):
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        sql = sql.replace("?", "%s")
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(sql, args)
    if commit:
        conn.commit()
        rowid = None
        if db_url:
            try:
                cur.execute("SELECT lastval()")
                row = cur.fetchone()
                rowid = row["lastval"] if isinstance(row, dict) else row[0]
            except Exception:
                pass
        else:
            rowid = cur.lastrowid
        conn.close()
        return rowid
    rv = cur.fetchone() if one else cur.fetchall()
    conn.close()
    if rv is None:
        return None
    if one:
        return dict(rv)
    return [dict(r) for r in rv]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ── DB init (runs on every cold start, safe due to IF NOT EXISTS) ─────────────
def init_db():
    db_url = os.environ.get("DATABASE_URL", "")
    conn = get_db()
    cur  = conn.cursor()

    if db_url:
        # PostgreSQL
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
            admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
            cur.execute(
                "INSERT INTO users (username, password_hash, email, role) VALUES (%s, %s, %s, 'admin')",
                ("admin", generate_password_hash(admin_pass), "admin@logisticsroyal.com")
            )
    else:
        # SQLite
        conn.executescript("""
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
        """)
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cur.fetchone():
            admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
            cur.execute(
                "INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, 'admin')",
                ("admin", generate_password_hash(admin_pass), "admin@logisticsroyal.com")
            )

    conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"[DB INIT ERROR] {e}")


# ── Auth decorator ────────────────────────────────────────────────────────────
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ── Public pages ──────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    sent = False
    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        email   = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if name and email and message:
            def _send():
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"[Logistics Royal Contact] {subject or 'New Enquiry'}"
                    msg["From"]    = email_config.MAIL_SENDER
                    msg["To"]      = email_config.MAIL_SENDER
                    html = f"""
                    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
                      <div style="background:#1e3a5f;padding:24px 32px">
                        <h1 style="color:#fff;margin:0;font-size:20px">&#128231; New Contact Form</h1>
                      </div>
                      <div style="padding:28px;font-size:14px;color:#334155">
                        <p><strong>Name:</strong> {name}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Subject:</strong> {subject or 'N/A'}</p>
                        <p><strong>Message:</strong></p>
                        <div style="background:#f1f5f9;padding:16px;border-radius:8px">{message}</div>
                      </div>
                    </div>
                    """
                    msg.attach(MIMEText(html, "html"))
                    with smtplib.SMTP_SSL(email_config.MAIL_SMTP, email_config.MAIL_PORT) as s:
                        s.login(email_config.MAIL_SENDER, email_config.MAIL_PASSWORD)
                        s.sendmail(email_config.MAIL_SENDER, email_config.MAIL_SENDER, msg.as_string())
                except Exception as e:
                    print(f"[CONTACT EMAIL ERROR] {e}")
            if email_config.MAIL_ENABLED:
                threading.Thread(target=_send, daemon=True).start()
            sent = True
    return render_template("contact.html", sent=sent)

@app.route("/track", methods=["GET", "POST"])
def public_track():
    result, history, error, tracking_number = None, [], None, ""
    if request.method == "POST":
        tracking_number = request.form.get("tracking_number", "").strip().upper()
        shipment = query("SELECT * FROM shipments WHERE tracking_number = ?",
                         (tracking_number,), one=True)
        if shipment:
            history = query(
                "SELECT * FROM shipment_history WHERE shipment_id = ? ORDER BY updated_at ASC",
                (shipment["id"],)
            )
            result = shipment
        else:
            error = f'No shipment found for "{tracking_number}". Please check and try again.'
    return render_template("public_track.html",
                           result=result, history=history,
                           error=error, tracking_number=tracking_number)


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard") if session["role"] == "admin"
                        else url_for("client_dashboard"))
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = query("SELECT * FROM users WHERE username = ?", (username,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("admin_dashboard") if user["role"] == "admin"
                            else url_for("client_dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ── Admin ─────────────────────────────────────────────────────────────────────
@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    clients = query("SELECT id, username, email FROM users WHERE role = 'client'")
    shipments = query("""
        SELECT s.id, s.tracking_number, s.current_status, s.created_at,
               s.destination_address, s.weight_kg, s.height_cm, s.width_cm,
               s.length_cm, s.description, s.package_type, s.image_filename,
               u.username
        FROM shipments s JOIN users u ON s.client_id = u.id
        ORDER BY s.created_at DESC
    """)
    return render_template("admin.html", clients=clients, shipments=shipments)

@app.route("/admin/create_client", methods=["POST"])
@login_required(role="admin")
def create_client():
    username = request.form["username"].strip()
    email    = request.form["email"].strip()
    password = request.form["password"]
    if query("SELECT id FROM users WHERE username = ?", (username,), one=True):
        flash("Username already exists.")
        return redirect(url_for("admin_dashboard"))
    query(
        "INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, 'client')",
        (username, generate_password_hash(password), email),
        commit=True
    )
    flash(f"Client '{username}' created successfully.")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/create_shipment", methods=["POST"])
@login_required(role="admin")
def create_shipment():
    client_id           = request.form["client_id"]
    destination_address = request.form["destination_address"].strip()
    description         = request.form.get("description", "").strip()
    package_type        = request.form.get("package_type", "").strip()
    weight_kg           = request.form.get("weight_kg", 0) or 0
    height_cm           = request.form.get("height_cm", 0) or 0
    width_cm            = request.form.get("width_cm",  0) or 0
    length_cm           = request.form.get("length_cm", 0) or 0
    tracking_number     = "TRK-" + uuid.uuid4().hex[:8].upper()

    image_filename = ""
    file = request.files.get("package_image")
    if file and file.filename and allowed_file(file.filename):
        ext            = file.filename.rsplit(".", 1)[1].lower()
        image_filename = f"{tracking_number}.{ext}"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))

    query(
        """INSERT INTO shipments
           (tracking_number, client_id, current_status, destination_address,
            weight_kg, height_cm, width_cm, length_cm,
            description, package_type, image_filename)
           VALUES (?, ?, 'Pending', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tracking_number, client_id, destination_address,
         weight_kg, height_cm, width_cm, length_cm,
         description, package_type, image_filename),
        commit=True
    )
    flash(f"Shipment {tracking_number} created and assigned.")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/update_location", methods=["POST"])
@login_required(role="admin")
def update_location():
    shipment_id  = request.form["shipment_id"]
    city_name    = request.form["city_name"].strip()
    status_notes = request.form["status_notes"].strip()
    query(
        "INSERT INTO shipment_history (shipment_id, city_name, status_notes) VALUES (?, ?, ?)",
        (shipment_id, city_name, status_notes), commit=True
    )
    query("UPDATE shipments SET current_status = ? WHERE id = ?",
          (status_notes, shipment_id), commit=True)
    row = query("""
        SELECT u.email, u.username, s.tracking_number
        FROM shipments s JOIN users u ON s.client_id = u.id WHERE s.id = ?
    """, (shipment_id,), one=True)
    if row:
        _send_update_email(row["email"], row["username"],
                           row["tracking_number"], city_name, status_notes)
    flash("Location updated and client notified by email.")
    return redirect(url_for("admin_dashboard"))


# ── Client ────────────────────────────────────────────────────────────────────
@app.route("/client")
@login_required(role="client")
def client_dashboard():
    shipments = query(
        "SELECT * FROM shipments WHERE client_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    )
    return render_template("client.html", shipments=shipments)

@app.route("/client/track/<int:shipment_id>")
@login_required(role="client")
def track_shipment(shipment_id):
    shipment = query(
        "SELECT * FROM shipments WHERE id = ? AND client_id = ?",
        (shipment_id, session["user_id"]), one=True
    )
    if not shipment:
        flash("Shipment not found.")
        return redirect(url_for("client_dashboard"))
    shipment_history = query(
        "SELECT * FROM shipment_history WHERE shipment_id = ? ORDER BY updated_at ASC",
        (shipment_id,)
    )
    return render_template("tracking.html", shipment=shipment,
                           shipment_history=shipment_history)


# ── Email helper ──────────────────────────────────────────────────────────────
def _send_update_email(to_email, username, tracking_number, city, status):
    if not email_config.MAIL_ENABLED:
        return
    def _send():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Logistics Royal Update: {tracking_number} — {status}"
            msg["From"]    = email_config.MAIL_SENDER
            msg["To"]      = to_email
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
                        border:1px solid #e2e8f0;border-radius:12px;overflow:hidden">
              <div style="background:#1e3a5f;padding:24px 32px">
                <h1 style="color:#fff;margin:0;font-size:22px">&#128230; Logistics Royal</h1>
                <p style="color:#93c5fd;margin:6px 0 0;font-size:13px">Shipment Status Update</p>
              </div>
              <div style="padding:32px">
                <p style="color:#334155;font-size:15px">Hi <strong>{username}</strong>,</p>
                <div style="background:#f1f5f9;border-radius:10px;padding:20px;margin:20px 0">
                  <table style="width:100%;font-size:14px;color:#334155">
                    <tr><td style="padding:6px 0;color:#64748b">Tracking Number</td>
                        <td style="font-weight:700;font-family:monospace">{tracking_number}</td></tr>
                    <tr><td style="padding:6px 0;color:#64748b">Current Location</td>
                        <td style="font-weight:600">&#128205; {city}</td></tr>
                    <tr><td style="padding:6px 0;color:#64748b">Status</td>
                        <td><span style="background:#dbeafe;color:#1d4ed8;padding:3px 10px;
                                         border-radius:20px;font-size:12px;font-weight:600">{status}</span></td></tr>
                  </table>
                </div>
                <a href="{os.environ.get('APP_URL','https://your-app.vercel.app')}/track"
                   style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
                          padding:12px 28px;border-radius:8px;font-weight:600;font-size:14px">
                  View Live Tracking &#8594;
                </a>
              </div>
            </div>
            """
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP_SSL(email_config.MAIL_SMTP, email_config.MAIL_PORT) as s:
                s.login(email_config.MAIL_SENDER, email_config.MAIL_PASSWORD)
                s.sendmail(email_config.MAIL_SENDER, to_email, msg.as_string())
        except Exception as e:
            print(f"[EMAIL ERROR] {e}")
    threading.Thread(target=_send, daemon=True).start()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
