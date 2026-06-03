"""
NovoForm — Authentication & Audit Manager
SQLite-backed user store + audit log.  No external dependencies.

DB        : <app>/data/novoform_auth.db          (shared, all users)
Text logs : <OS AppData>/NovoForm/logs/<username>/YYYY-MM-DD.txt
            Windows : %APPDATA%\\NovoForm\\logs\\<username>\\
            macOS   : ~/Library/Application Support/NovoForm/logs/<username>/
            Linux   : ~/.novoform/logs/<username>/
            → hidden from regular users; readable by admin via Admin Panel
"""
import csv
import hashlib
import io
import os
import secrets
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "novoform_auth.db"


def _appdata_logs_root() -> Path:
    """Return the OS-appropriate hidden base dir for log files."""
    if os.name == "nt":                           # Windows
        base = Path(os.environ.get("APPDATA", Path.home())) / "NovoForm" / "logs"
    elif sys.platform == "darwin":                # macOS
        base = Path.home() / "Library" / "Application Support" / "NovoForm" / "logs"
    else:                                         # Linux / other
        base = Path.home() / ".novoform" / "logs"
    return base


def _user_log_dir(username: str) -> Path:
    """Per-user log folder, created on demand."""
    d = _appdata_logs_root() / username
    d.mkdir(parents=True, exist_ok=True)
    return d

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "nova@123"


# ── helpers ───────────────────────────────────────────────────────────────────

def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _new_salt() -> str:
    return secrets.token_hex(16)


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _get_host_ip() -> tuple[str, str]:
    """Returns (hostname, ip_address)."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    try:
        ip = socket.gethostbyname(hostname)
        # On some machines gethostbyname returns 127.0.0.1 — try harder
        if ip.startswith("127."):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
    except Exception:
        ip = "unknown"
    return hostname, ip


# ── initialisation ────────────────────────────────────────────────────────────

def initialize_db() -> None:
    """Create tables and default admin on first run."""
    con = _conn()
    cur = con.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            full_name     TEXT    NOT NULL,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'user',
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    NOT NULL,
            created_by    TEXT    NOT NULL DEFAULT 'system'
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL,
            username   TEXT NOT NULL,
            full_name  TEXT NOT NULL,
            action     TEXT NOT NULL,
            details    TEXT,
            hostname   TEXT,
            ip_address TEXT
        );
    """)

    # Add ip_address column to older DBs that only have 'host'
    try:
        cur.execute("ALTER TABLE audit_logs ADD COLUMN ip_address TEXT")
        con.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        cur.execute("ALTER TABLE audit_logs RENAME COLUMN host TO hostname")
        con.commit()
    except sqlite3.OperationalError:
        pass  # already renamed or column name differs — ignore

    # Create default admin if no users exist yet
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        salt = _new_salt()
        cur.execute(
            "INSERT INTO users (username, full_name, password_hash, salt, role, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (DEFAULT_ADMIN_USER, "Administrator",
             _hash(DEFAULT_ADMIN_PASS, salt), salt,
             "admin", _now(), "system")
        )
        con.commit()

    con.close()


# ── authentication ────────────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> dict | None:
    """Returns user dict {id, username, full_name, role} on success, else None."""
    con = _conn()
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM users WHERE username=? AND active=1",
        (username.strip().lower(),)
    )
    row = cur.fetchone()
    con.close()

    if row is None:
        return None
    if _hash(password, row["salt"]) != row["password_hash"]:
        return None

    return {
        "id":        row["id"],
        "username":  row["username"],
        "full_name": row["full_name"],
        "role":      row["role"],
    }


# ── user management ───────────────────────────────────────────────────────────

def add_user(username: str, full_name: str, password: str,
             role: str, created_by: str) -> tuple[bool, str]:
    uname = username.strip().lower()
    if not uname or not password or not full_name:
        return False, "Username, full name and password are required."
    if role not in ("admin", "user"):
        return False, "Role must be 'admin' or 'user'."

    salt = _new_salt()
    try:
        con = _conn()
        con.execute(
            "INSERT INTO users (username, full_name, password_hash, salt, role, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (uname, full_name.strip(), _hash(password, salt), salt,
             role, _now(), created_by)
        )
        con.commit()
        con.close()
        return True, f"User '{uname}' created."
    except sqlite3.IntegrityError:
        return False, f"Username '{uname}' already exists."
    except Exception as e:
        return False, str(e)


def deactivate_user(username: str) -> tuple[bool, str]:
    con = _conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET active=0 WHERE username=? AND role!='admin'",
                (username,))
    affected = cur.rowcount
    con.commit()
    con.close()
    if affected == 0:
        return False, "User not found or cannot deactivate an admin."
    return True, f"User '{username}' deactivated."


def reactivate_user(username: str) -> tuple[bool, str]:
    con = _conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET active=1 WHERE username=?", (username,))
    affected = cur.rowcount
    con.commit()
    con.close()
    if affected == 0:
        return False, "User not found."
    return True, f"User '{username}' reactivated."


def reset_password(username: str, new_password: str, by_whom: str) -> tuple[bool, str]:
    if not new_password:
        return False, "Password cannot be empty."
    salt = _new_salt()
    con = _conn()
    cur = con.cursor()
    cur.execute(
        "UPDATE users SET password_hash=?, salt=? WHERE username=?",
        (_hash(new_password, salt), salt, username)
    )
    affected = cur.rowcount
    con.commit()
    con.close()
    if affected == 0:
        return False, "User not found."
    log_action(by_whom, by_whom, "PASSWORD_RESET",
               f"Reset password for user '{username}'")
    return True, f"Password reset for '{username}'."


def get_all_users() -> list[dict]:
    con = _conn()
    cur = con.cursor()
    cur.execute(
        "SELECT id, username, full_name, role, active, created_at, created_by "
        "FROM users ORDER BY id"
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


# ── audit log — SQLite ────────────────────────────────────────────────────────

def log_action(username: str, full_name: str,
               action: str, details: str = "") -> None:
    hostname, ip = _get_host_ip()
    ts = _now()

    # 1. Write to SQLite
    try:
        con = _conn()
        con.execute(
            "INSERT INTO audit_logs "
            "(timestamp, username, full_name, action, details, hostname, ip_address) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, username, full_name, action, details, hostname, ip)
        )
        con.commit()
        con.close()
    except Exception:
        pass   # never crash the app on audit failure

    # 2. Append to per-user daily text log in OS AppData (hidden from regular users)
    _write_daily_log(ts, username, full_name, action, details, hostname, ip)


def _write_daily_log(ts: str, username: str, full_name: str,
                     action: str, details: str,
                     hostname: str, ip: str) -> None:
    """
    Append one line to:
      Windows : %APPDATA%\\NovoForm\\logs\\<username>\\YYYY-MM-DD.txt
      macOS   : ~/Library/Application Support/NovoForm/logs/<username>/YYYY-MM-DD.txt
    One file per day per user, stored in OS AppData — not visible in the app folder.
    """
    try:
        log_file = _user_log_dir(username) / f"{_today()}.txt"
        line = (
            f"[{ts}]  "
            f"User: {username} ({full_name})  |  "
            f"Action: {action}  |  "
            f"Details: {details or '-'}  |  "
            f"Host: {hostname}  |  "
            f"IP: {ip}\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ── audit log — queries ───────────────────────────────────────────────────────

def get_audit_logs(limit: int = 1000,
                   username_filter: str = "") -> list[dict]:
    con = _conn()
    cur = con.cursor()
    if username_filter:
        cur.execute(
            "SELECT * FROM audit_logs WHERE username=? "
            "ORDER BY id DESC LIMIT ?",
            (username_filter, limit)
        )
    else:
        cur.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,)
        )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def export_logs_csv(rows: list[dict]) -> str:
    """Return CSV string for the given rows list."""
    if not rows:
        return ""
    output = io.StringIO()
    cols = ["id", "timestamp", "username", "full_name",
            "action", "details", "hostname", "ip_address"]
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore",
                            lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def get_daily_log_files(username: str = "") -> list[tuple[str, Path]]:
    """
    Return list of (username, path) tuples for daily log files, newest first.
    If username given → only that user's files.
    If blank → all users on this machine (for admin view).
    """
    root = _appdata_logs_root()
    if not root.exists():
        return []

    results: list[tuple[str, Path]] = []
    if username:
        user_dir = root / username
        if user_dir.exists():
            results = [(username, p) for p in user_dir.glob("*.txt")]
    else:
        # All user sub-folders
        for user_dir in root.iterdir():
            if user_dir.is_dir():
                uname = user_dir.name
                results.extend((uname, p) for p in user_dir.glob("*.txt"))

    # Sort newest date first
    results.sort(key=lambda x: x[1].stem, reverse=True)
    return results
