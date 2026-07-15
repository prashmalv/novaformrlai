"""
NovoForm — Authentication & Audit Manager
SQLite-backed user store + audit log.

Mode resolution (in priority order):
  1. config/api_config.json → "server_url"      (HTTP server mode — RECOMMENDED)
     e.g. http://192.168.1.101:8765
     Admin machine runs server.py / start_server.bat
  2. config/api_config.json → "central_db_path" (legacy UNC file share — needs creds)
  3. data/novoform_auth.db                       (local only — single machine)

Text logs : <OS AppData>/NovoForm/logs/<username>/YYYY-MM-DD.txt  (always local per machine)

HTTP server mode:
  - No Windows credential prompts
  - Works across WiFi and LAN
  - Admin sees all machines' users and audit logs in one place
  - Falls back to local DB if server unreachable
"""
import csv
import hashlib
import io
import json
import os
import secrets
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_APP_ROOT   = Path(__file__).parent.parent.parent
_LOCAL_DB   = _APP_ROOT / "data" / "novoform_auth.db"
_API_CONFIG = _APP_ROOT / "config" / "api_config.json"


# ── Server mode helpers ────────────────────────────────────────────────────────

def _get_server_url() -> str | None:
    """Return HTTP server URL if configured, else None."""
    try:
        if _API_CONFIG.exists():
            cfg = json.loads(_API_CONFIG.read_text())
            url = cfg.get("server_url", "").strip().rstrip("/")
            return url if url else None
    except Exception:
        pass
    return None


def _srv(method: str, endpoint: str, payload: dict = None,
         admin_user: str = "", admin_pass: str = "",
         timeout: float = 5.0) -> dict | list | None:
    """
    HTTP call to auth server. Returns parsed JSON or None on any failure.
    Uses stdlib urllib so no extra dependencies needed on client machines.
    """
    base = _get_server_url()
    if not base:
        return None
    import urllib.request, urllib.error
    url = f"{base}{endpoint}"
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"}
    if admin_user:
        headers["x-admin-user"] = admin_user
        headers["x-admin-pass"] = admin_pass
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def ping_server() -> tuple[bool, str]:
    """Check if server is reachable. Returns (ok, status_message)."""
    url = _get_server_url()
    if not url:
        return False, "No server URL configured."
    result = _srv("GET", "/health", timeout=3.0)
    if result and result.get("status") == "ok":
        return True, f"Connected  ·  NovoForm Server v{result.get('version', '?')}"
    return False, f"Server not reachable at {url}"


def set_server_url(url: str) -> tuple[bool, str]:
    """Save server_url to api_config.json. Pass empty string to disable."""
    url = url.strip().rstrip("/")
    try:
        _API_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if _API_CONFIG.exists():
            try:
                existing = json.loads(_API_CONFIG.read_text())
            except Exception:
                pass
        existing["server_url"] = url
        _API_CONFIG.write_text(json.dumps(existing, indent=2))
        if url:
            return True, "Server URL saved. Restart the app to apply."
        return True, "Reverted to local / file-share mode."
    except Exception as e:
        return False, str(e)


# ── Local DB path (used when server mode not active) ──────────────────────────

def _get_db_path() -> Path:
    """Return central DB path if configured, else local path."""
    try:
        if _API_CONFIG.exists():
            cfg = json.loads(_API_CONFIG.read_text())
            central = cfg.get("central_db_path", "").strip()
            if central:
                return Path(central)
    except Exception:
        pass
    return _LOCAL_DB


def get_db_location() -> dict:
    """Return info about the current connection mode (used by admin panel UI)."""
    srv_url = _get_server_url()
    if srv_url:
        ok, msg = ping_server()
        return {
            "mode":       "server",
            "path":       srv_url,
            "is_central": True,
            "reachable":  ok,
            "label":      f"HTTP Server: {srv_url}",
            "status_msg": msg,
        }
    path = _get_db_path()
    is_central = path != _LOCAL_DB
    return {
        "mode":       "central_db" if is_central else "local",
        "path":       str(path),
        "is_central": is_central,
        "reachable":  path.exists() or path.parent.exists(),
        "label":      "Central DB (file share)" if is_central else "Local (this machine only)",
        "status_msg": "",
    }


def set_central_db_path(new_path: str) -> tuple[bool, str]:
    """
    Save a new central_db_path to api_config.json.
    Pass empty string to revert to local DB.
    """
    new_path = new_path.strip()
    if new_path:
        p = Path(new_path)
        if not p.parent.exists():
            return False, f"Folder not found: {p.parent}"
    try:
        _API_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if _API_CONFIG.exists():
            try:
                existing = json.loads(_API_CONFIG.read_text())
            except Exception:
                pass
        existing["central_db_path"] = new_path
        _API_CONFIG.write_text(json.dumps(existing, indent=2))
        return True, "Saved. Restart the application to apply." if new_path else "Reverted to local database."
    except Exception as e:
        return False, str(e)


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
    db = _get_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
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
    """
    Returns user dict {id, username, full_name, role} on success, else None.
    In server mode: calls /auth/login (server also logs the login event).
    Falls back to local DB if server unreachable.
    """
    hostname, ip = _get_host_ip()
    srv_result = _srv("POST", "/auth/login", {
        "username":   username.strip().lower(),
        "password":   password,
        "hostname":   hostname,
        "ip_address": ip,
    })
    if srv_result is not None:
        return srv_result  # server authenticated and logged the event

    # ── Local DB fallback ──────────────────────────────────────────────────────
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
             role: str, created_by: str,
             _admin_user: str = "", _admin_pass: str = "") -> tuple[bool, str]:
    uname = username.strip().lower()
    if not uname or not password or not full_name:
        return False, "Username, full name and password are required."
    if role not in ("admin", "user"):
        return False, "Role must be 'admin' or 'user'."

    # Server mode: admin credentials required for the HTTP call
    result = _srv("POST", "/users", {
        "username": uname, "full_name": full_name.strip(),
        "password": password, "role": role,
    }, admin_user=_admin_user, admin_pass=_admin_pass)
    if result is not None:
        return True, result.get("message", f"User '{uname}' created.")

    # Local fallback
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


def deactivate_user(username: str,
                    _admin_user: str = "", _admin_pass: str = "") -> tuple[bool, str]:
    result = _srv("PUT", f"/users/{username}/deactivate",
                  admin_user=_admin_user, admin_pass=_admin_pass)
    if result is not None:
        return True, result.get("message", f"User '{username}' deactivated.")

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


def reactivate_user(username: str,
                    _admin_user: str = "", _admin_pass: str = "") -> tuple[bool, str]:
    result = _srv("PUT", f"/users/{username}/reactivate",
                  admin_user=_admin_user, admin_pass=_admin_pass)
    if result is not None:
        return True, result.get("message", f"User '{username}' reactivated.")

    con = _conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET active=1 WHERE username=?", (username,))
    affected = cur.rowcount
    con.commit()
    con.close()
    if affected == 0:
        return False, "User not found."
    return True, f"User '{username}' reactivated."


def reset_password(username: str, new_password: str, by_whom: str,
                   _admin_user: str = "", _admin_pass: str = "") -> tuple[bool, str]:
    if not new_password:
        return False, "Password cannot be empty."

    result = _srv("PUT", f"/users/{username}/password",
                  {"new_password": new_password, "by_whom": by_whom},
                  admin_user=_admin_user, admin_pass=_admin_pass)
    if result is not None:
        return True, result.get("message", f"Password reset for '{username}'.")

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


def get_all_users(_admin_user: str = "", _admin_pass: str = "") -> list[dict]:
    result = _srv("GET", "/users",
                  admin_user=_admin_user, admin_pass=_admin_pass)
    if result is not None:
        return result

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

    # 1. Always write local daily text log (offline audit trail)
    _write_daily_log(ts, username, full_name, action, details, hostname, ip)

    # 2. Server mode: send to central server (short timeout — non-blocking feel)
    srv_result = _srv("POST", "/audit", {
        "username":  username,
        "full_name": full_name,
        "action":    action,
        "details":   details,
    }, timeout=1.5)
    if srv_result is not None:
        return  # server wrote it centrally

    # 3. Fallback: write to local SQLite
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

def get_audit_logs(limit: int = 1000, username_filter: str = "",
                   _admin_user: str = "", _admin_pass: str = "") -> list[dict]:
    # Server mode: fetch from central server
    endpoint = f"/audit?limit={limit}"
    result = _srv("GET", endpoint,
                  admin_user=_admin_user, admin_pass=_admin_pass)
    if result is not None:
        if username_filter:
            result = [r for r in result if r.get("username") == username_filter]
        return result

    # Local fallback
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
