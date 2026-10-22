import os
import hmac
import secrets
from pathlib import Path
from functools import wraps
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask, request, session, redirect, url_for,
    render_template_string, abort, jsonify
)
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

if len(SECRET_KEY) < 32 or not ADMIN_PASSWORD or not DATABASE_URL:
    raise RuntimeError(
        "FLASK_SECRET_KEY, ADMIN_PASSWORD aur DATABASE_URL environment variables set karo."
    )

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    MAX_CONTENT_LENGTH=20 * 1024
)


@contextmanager
def get_db():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=RealDictCursor,
        connect_timeout=10
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def valid_csrf():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(supplied, expected)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def home():
    from flask import send_from_directory
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/csrf")
def get_csrf():
    return jsonify({"csrf_token": csrf_token()})


@app.post("/send-message")
def send_message():
    if not valid_csrf():
        abort(400, "Page refresh karke dobara try karo.")

    name = request.form.get("name", "").strip()
    message = request.form.get("message", "").strip()

    if not name or len(name) > 60 or not message or len(message) > 1000:
        abort(400, "Name ya message ki length galat hai.")

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (name, message, created_at) VALUES (%s, %s, %s)",
                (
                    name,
                    message,
                    datetime.now(timezone.utc).isoformat(timespec="seconds")
                )
            )

    return """
    <!doctype html>
    <html lang="en">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Message Sent</title>
    <body style="background:#09070c;color:white;font-family:sans-serif;text-align:center;padding:50px">
    <h1 style="color:#d7a642">Message sent successfully!</h1>
    <a style="color:#e5b94d" href="/">Back to fanpage</a>
    </body>
    </html>
    """


LOGIN_PAGE = """
<!doctype html>
<html lang="en">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin Login</title>
<body style="background:#09070c;color:white;font-family:sans-serif;max-width:400px;margin:70px auto;padding:20px">
<h1 style="color:#d7a642">Realm Admin</h1>
{% if error %}<p style="color:#ff7777">{{ error }}</p>{% endif %}
<form method="post">
<input type="hidden" name="csrf_token" value="{{ token }}">
<label>Admin password</label><br><br>
<input type="password" name="password" required style="box-sizing:border-box;width:100%;padding:12px">
<br><br><button style="padding:12px 20px">Login</button>
</form>
</body>
</html>
"""


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        if not valid_csrf():
            abort(400, "Page refresh karke dobara try karo.")

        password = request.form.get("password", "")
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session["admin_logged_in"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("admin"))
        error = "Incorrect password."

    return render_template_string(
        LOGIN_PAGE, error=error, token=csrf_token()
    )


@app.get("/admin")
@admin_required
def admin():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, name, message, created_at FROM messages ORDER BY id DESC"
            )
            messages = cur.fetchall()

    page = """
    <!doctype html>
    <html lang="en">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Messages Admin</title>
    <body style="background:#09070c;color:white;font-family:sans-serif;padding:20px">
    <h1 style="color:#d7a642">Fanpage Messages</h1>
    <form method="post" action="/admin/logout">
      <input type="hidden" name="csrf_token" value="{{ token }}">
      <button>Logout</button>
    </form>
    {% for m in messages %}
      <article style="border:1px solid #6b4b27;padding:15px;margin:18px 0;border-radius:8px">
        <h3>{{ m['name'] }}</h3>
        <p style="white-space:pre-wrap;overflow-wrap:anywhere">{{ m['message'] }}</p>
        <small>{{ m['created_at'] }}</small>
        <form method="post" action="/admin/delete/{{ m['id'] }}">
          <input type="hidden" name="csrf_token" value="{{ token }}">
          <button style="margin-top:12px">Delete message</button>
        </form>
      </article>
    {% else %}
      <p>No messages yet.</p>
    {% endfor %}
    </body></html>
    """
    return render_template_string(page, messages=messages, token=csrf_token())


@app.post("/admin/delete/<int:message_id>")
@admin_required
def delete_message(message_id):
    if not valid_csrf():
        abort(400, "Page refresh karke dobara try karo.")

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("DELETE FROM messages WHERE id = %s", (message_id,))
    return redirect(url_for("admin"))


@app.post("/admin/logout")
@admin_required
def admin_logout():
    if not valid_csrf():
        abort(400, "Page refresh karke dobara try karo.")
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/<path:filename>")
def existing_files(filename):
    from flask import send_from_directory

    if any(part.startswith(".") for part in Path(filename).parts):
        abort(404)

    return send_from_directory(BASE_DIR, filename)


# Create the table in Neon when the app starts.
init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        debug=False
    )
