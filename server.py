"""
NovoForm Auth Server — Run this on the Admin machine only.
Worker machines connect via HTTP instead of Windows file share.

Usage:
  Double-click  start_server.bat
  Or manually:  venv\Scripts\python.exe server.py

Listens on 0.0.0.0:8765 — all machines on the LAN can reach it.
Admin Panel → Database Settings → enter: http://<THIS-MACHINE-IP>:8765
"""
import sys
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from src.auth import auth_manager

auth_manager.initialize_db()

app = FastAPI(title="NovoForm Auth Server", version="1.3")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────────────────────

class LoginReq(BaseModel):
    username: str
    password: str
    hostname: str = ""
    ip_address: str = ""

class AddUserReq(BaseModel):
    username: str
    full_name: str
    password: str
    role: str = "user"

class ResetPassReq(BaseModel):
    new_password: str
    by_whom: str

class AuditReq(BaseModel):
    username: str
    full_name: str
    action: str
    details: str = ""


# ── Admin header check ─────────────────────────────────────────────────────────

def _require_admin(user: str, pwd: str) -> dict:
    u = auth_manager.authenticate(user, pwd)
    if not u or u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin credentials required")
    return u


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.3", "service": "NovoForm Auth Server"}


@app.post("/auth/login")
def login(body: LoginReq):
    user = auth_manager.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    # Server writes login log so all machines' logins appear in one place
    auth_manager.log_action(
        body.username, user.get("full_name", ""),
        "LOGIN", f"from {body.hostname} ({body.ip_address})",
    )
    return user


@app.get("/users")
def list_users(
    x_admin_user: str = Header(...),
    x_admin_pass: str = Header(...),
):
    _require_admin(x_admin_user, x_admin_pass)
    return auth_manager.get_all_users()


@app.post("/users")
def add_user(
    body: AddUserReq,
    x_admin_user: str = Header(...),
    x_admin_pass: str = Header(...),
):
    adm = _require_admin(x_admin_user, x_admin_pass)
    ok, msg = auth_manager.add_user(
        body.username, body.full_name, body.password,
        body.role, created_by=adm["username"],
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.put("/users/{username}/password")
def reset_password(
    username: str,
    body: ResetPassReq,
    x_admin_user: str = Header(...),
    x_admin_pass: str = Header(...),
):
    _require_admin(x_admin_user, x_admin_pass)
    ok, msg = auth_manager.reset_password(username, body.new_password, body.by_whom)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.put("/users/{username}/deactivate")
def deactivate(
    username: str,
    x_admin_user: str = Header(...),
    x_admin_pass: str = Header(...),
):
    _require_admin(x_admin_user, x_admin_pass)
    ok, msg = auth_manager.deactivate_user(username)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.put("/users/{username}/reactivate")
def reactivate(
    username: str,
    x_admin_user: str = Header(...),
    x_admin_pass: str = Header(...),
):
    _require_admin(x_admin_user, x_admin_pass)
    ok, msg = auth_manager.reactivate_user(username)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/audit")
def add_audit(body: AuditReq):
    # Called by worker machines to log their actions centrally
    auth_manager.log_action(
        body.username, body.full_name, body.action, body.details,
    )
    return {"ok": True}


@app.get("/audit")
def get_audit(
    limit: int = 500,
    x_admin_user: str = Header(...),
    x_admin_pass: str = Header(...),
):
    _require_admin(x_admin_user, x_admin_pass)
    return auth_manager.get_audit_logs(limit=limit)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if host_ip.startswith("127."):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
            s.close()
    except Exception:
        host_ip = "localhost"

    print("\n" + "=" * 55)
    print("  NovoForm Auth Server  v1.3")
    print("  Nova Formworks Pvt. Ltd.")
    print("=" * 55)
    print(f"  Server address  : http://0.0.0.0:8765")
    print(f"  Worker machines : http://{host_ip}:8765")
    print(f"  API docs        : http://{host_ip}:8765/docs")
    print("=" * 55)
    print("  Set this URL in each worker machine:")
    print(f"  Admin Panel → Database Settings → Server URL")
    print(f"  → http://{host_ip}:8765")
    print("=" * 55)
    print("  Press Ctrl+C to stop\n")

    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
