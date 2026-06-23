# NovoForm v1.3 — Deployment & Setup Guide
**Nova Formworks Pvt. Ltd.**  
Developed by RLAI (rightleft.ai) · Version 1.3 · June 2026

---

## Contents
1. [Prerequisites](#1-prerequisites)
2. [Install on First Machine (Admin)](#2-install-on-first-machine-admin)
3. [First Login & Default Credentials](#3-first-login--default-credentials)
4. [Create User Accounts](#4-create-user-accounts)
5. [Set Up Central / Shared Database (LAN)](#5-set-up-central--shared-database-lan)
6. [Install on Additional Worker Machines](#6-install-on-additional-worker-machines)
7. [Connect Worker Machines to Central Database](#7-connect-worker-machines-to-central-database)
8. [Daily Usage Flow](#8-daily-usage-flow)
9. [Troubleshooting](#9-troubleshooting)
10. [Quick Reference Card](#10-quick-reference-card)

---

## 1. Prerequisites

Install these **once** on **every** machine before running NovoForm.

### Python 3.10 or higher
1. Go to: **https://www.python.org/downloads/**
2. Download the latest Python 3.x installer for Windows
3. Run the installer
4. **IMPORTANT:** On the first screen, tick **"Add Python to PATH"** before clicking Install

   ```
   ┌─────────────────────────────────────────┐
   │  Install Python 3.x                     │
   │                                         │
   │  [✓] Add Python to PATH  ← TICK THIS   │
   │                                         │
   │  [ Install Now ]                        │
   └─────────────────────────────────────────┘
   ```

5. After install, open Command Prompt and verify:
   ```
   python --version
   ```
   Should show: `Python 3.10.x` or higher

### Internet Connection (first install only)
Required only during the first installation to download Python packages (PyQt6, ezdxf, ReportLab, etc.). After that, no internet needed.

---

## 2. Install on First Machine (Admin)

The **Admin machine** is the main machine (usually Yukti's / senior team member's PC). It will host the shared database.

### Steps:
1. Copy the file `NovoForm_v1.3_Nova_UpdatedBranding.zip` to the machine
2. **Right-click → Extract All** → choose a permanent location, e.g.:
   ```
   C:\Nova\NovoForm\
   ```
   > ⚠ **Do NOT install inside Downloads or Desktop** — the app needs a stable, fixed folder path.

3. Open the extracted folder. You should see:
   ```
   C:\Nova\NovoForm\
   ├── main.py
   ├── requirements.txt
   ├── install_windows_nova_updatedbranding.bat
   ├── config\
   ├── src\
   └── assets\
   ```

4. **Double-click** `install_windows_nova_updatedbranding.bat`
5. A black Command Prompt window will open and run automatically (takes 3–5 minutes on first install)
6. When complete, you will see:
   ```
   Installation Complete! | NovoForm v1.3
   ```
7. A **"NovoForm" shortcut** is now on your Desktop
8. Click **OK / any key** to close the installer window

---

## 3. First Login & Default Credentials

Launch the app by double-clicking the **NovoForm** shortcut on the Desktop.

### Default Admin Login:

| Field    | Value       |
|----------|-------------|
| Username | `admin`     |
| Password | `nova@123`  |

> ⚠ **Change this password immediately after first login** (see step 4).

### How to change the admin password:
1. Login with `admin` / `nova@123`
2. Click **Admin Panel** (top menu or gear icon)
3. Go to **User Management** tab
4. Select `admin` → click **Reset Password**
5. Enter new password → Save

---

## 4. Create User Accounts

Only the **admin** can create user accounts. Do this after logging in on the Admin machine.

### Steps:
1. Login as `admin`
2. Open **Admin Panel** → **User Management** tab
3. Click **"+ Add User"**
4. Fill in the form:

   | Field      | Example        | Notes                          |
   |------------|----------------|--------------------------------|
   | Username   | `rahul`        | Lowercase, no spaces           |
   | Full Name  | `Rahul Sharma` | Shown in audit logs            |
   | Password   | `nova@2026`    | Share with user directly       |
   | Role       | `user`         | Use `admin` only for managers  |

5. Click **Save User**

### Roles:
| Role    | Can Do                                              |
|---------|-----------------------------------------------------|
| `admin` | Create/delete users, view all audit logs, change DB settings |
| `user`  | Import drawings, generate BOQ, export PDF/Excel/DXF |

> Recommended: Only 1–2 admin accounts. Rest of team = `user` role.

---

## 5. Set Up Central / Shared Database (LAN)

This step makes **all machines share one database** — same users, same audit logs, controlled from one place.

> If you only have **one machine**, skip this section. The app works standalone.

### On the Admin Machine:

**Step 5.1 — Create a shared folder:**

1. Create a new folder: `C:\NovaSharedDB\`
2. Copy the database file into it:
   ```
   From: C:\Nova\NovoForm\data\novoform_auth.db
   To:   C:\NovaSharedDB\novoform_auth.db
   ```
   > If `data\` folder does not exist yet, run the app once to create it.

**Step 5.2 — Share the folder on Windows:**

1. Right-click `C:\NovaSharedDB\` → **Properties**
2. Click **Sharing** tab → **Advanced Sharing**
3. Tick **"Share this folder"**
4. Share name: `NovaSharedDB` (no spaces)
5. Click **Permissions** → Add `Everyone` with **Read/Write** (or specific domain user)
6. Click **OK** → **Apply**

**Step 5.3 — Find the Admin machine's Computer Name:**

1. Press `Win + R` → type `sysdm.cpl` → Enter
2. Note the **Computer name**, e.g.: `ADMIN-PC` or `NOVA-DESKTOP-01`

The shared database path will be:
```
\\ADMIN-PC\NovaSharedDB\novoform_auth.db
```

**Step 5.4 — Tell NovoForm to use the shared database:**

1. Open NovoForm on the Admin machine
2. Login as `admin`
3. Go to **Admin Panel** → **Database Settings** tab
4. In the **"Set Central Database Path"** box, enter:
   ```
   \\ADMIN-PC\NovaSharedDB\novoform_auth.db
   ```
   (Replace `ADMIN-PC` with your actual computer name)
5. Click **"Save & Apply"**
6. App will show: **"Mode: Central shared database ✓"**
7. **Restart the app** for the change to take effect

---

## 6. Install on Additional Worker Machines

Repeat these steps for each additional machine (e.g., Rahul's PC, Priya's laptop).

1. Copy `NovoForm_v1.3_Nova_UpdatedBranding.zip` to the machine (USB drive, email, or shared folder)
2. Extract to: `C:\Nova\NovoForm\` (same path as admin machine — not mandatory but recommended for consistency)
3. Double-click `install_windows_nova_updatedbranding.bat`
4. Wait for installation to complete
5. Desktop shortcut created → app is ready to launch

---

## 7. Connect Worker Machines to Central Database

Do this on **every worker machine** after installation.

1. Open NovoForm → Login using the credentials admin gave you (e.g., `rahul` / `nova@2026`)
   > If the shared DB is not set yet, use `admin` / `nova@123` for first login
2. Go to **Admin Panel** → **Database Settings** tab
   > Note: `user` role can view but not change DB settings. Do this step while logged in as `admin`.
3. Enter the central database path:
   ```
   \\ADMIN-PC\NovaSharedDB\novoform_auth.db
   ```
4. Click **"Save & Apply"**
5. You'll see a confirmation message
6. **Close and reopen the app**
7. Login again — now using the centrally managed accounts

### How to verify it's working:
- Login as `admin` on Admin machine → add a new user
- Go to Worker machine → open NovoForm → the new user should be able to login

---

## 8. Daily Usage Flow

```
Worker logs in                Admin machine stays on
     ↓                              ↓
Import DXF/DWG             ← All audit logs go here
     ↓                         (shared DB)
Review elements
Add missing elements
     ↓
BOQ computed automatically
     ↓
Export:
  • BOQ PDF
  • Quotation PDF
  • Excel
  • Formwork DXF  ← NEW in v1.3
     ↓
Share with client
```

### File locations (on each machine):
| Item             | Location                            |
|------------------|-------------------------------------|
| App folder       | `C:\Nova\NovoForm\`                 |
| Shared database  | `\\ADMIN-PC\NovaSharedDB\novoform_auth.db` |
| Local DB backup  | `C:\Nova\NovoForm\data\novoform_auth.db` |
| Exported PDFs    | Wherever you save them (choose in dialog) |
| Audit logs (text)| `C:\Users\<name>\AppData\Roaming\NovoForm\logs\` |

---

## 9. Troubleshooting

### "Python not found" during install
→ Python not in PATH. Re-install Python from python.org and tick "Add to PATH".

### "Cannot connect to central database" / DB shows as "Not reachable"
→ Check these:
1. Admin machine is **switched on** and connected to LAN
2. `C:\NovaSharedDB\` folder is still shared (right-click → Properties → Sharing)
3. Computer name in the path is correct (`\\ADMIN-PC\...`)
4. Windows Firewall is not blocking file sharing (Control Panel → Firewall → Allow app → File and Printer Sharing)
5. Both machines are on the **same network** (same WiFi router or LAN cable)

If still not working, try the **IP address** instead of computer name:
```
\\192.168.1.101\NovaSharedDB\novoform_auth.db
```
(Find Admin machine's IP: press `Win + R` → `cmd` → type `ipconfig` → look for IPv4 Address)

### "Access Denied" when saving to shared folder
→ Sharing permissions need Read+Write. Redo Step 5.2 and set Full Control for Everyone.

### App opens but shows blank / crashes on start
→ Run from Command Prompt to see error:
```
cd C:\Nova\NovoForm
venv\Scripts\python.exe main.py
```
Send the error output to RLAI support.

### Forgot admin password
→ Delete `data\novoform_auth.db` file. Next launch will recreate it with default `admin` / `nova@123`. All previous users will be lost — recreate them.

### DXF file won't open in AutoCAD
→ The DXF is saved in R2010 format (AutoCAD 2010+). Works in AutoCAD 2010 and all later versions. Also opens in FreeCAD (free) and LibreCAD (free).

---

## 10. Quick Reference Card

> Print this section and keep it at the workstation.

```
┌─────────────────────────────────────────────────────────┐
│          NovoForm v1.3 — Quick Reference                │
│          Nova Formworks Pvt. Ltd.                       │
├─────────────────────────────────────────────────────────┤
│  DEFAULT LOGIN (change immediately after first use)     │
│  Username : admin                                       │
│  Password : nova@123                                    │
├─────────────────────────────────────────────────────────┤
│  CENTRAL DATABASE PATH                                  │
│  \\<ADMIN-PC-NAME>\NovaSharedDB\novoform_auth.db        │
│                                                         │
│  Actual path used: ______________________________       │
│  Admin machine IP: ______________________________       │
├─────────────────────────────────────────────────────────┤
│  WHERE TO SET IT                                        │
│  Admin Panel → Database Settings → Enter path → Save   │
├─────────────────────────────────────────────────────────┤
│  USER ACCOUNTS CREATED                                  │
│  1. _____________ / Role: _______ / Machine: _______   │
│  2. _____________ / Role: _______ / Machine: _______   │
│  3. _____________ / Role: _______ / Machine: _______   │
├─────────────────────────────────────────────────────────┤
│  SUPPORT: rightleft.ai (RLAI)                          │
│  App installed at: C:\Nova\NovoForm\                   │
└─────────────────────────────────────────────────────────┘
```

---

## Appendix: What's New in v1.3

| Feature | Description |
|---|---|
| **Add Missing Element** | In Review Dialog, click "+ Add Missing Element" to manually add columns/walls not detected in drawing |
| **Export Formwork DXF** | Export tab → generates AutoCAD DXF with panel layouts, OC corners, waller positions, tierod circles, BOQ table, title block |
| **Non-standard panel warning** | Panels outside Nova catalog highlighted orange in BOQ with warning banner |
| **Auto-detect panel height** | Scans drawing text for panel height annotations |
| **Live BOQ update** | Change panel height dropdown → BOQ recalculates instantly |

---

*Document version: 1.3 · Date: June 2026 · RLAI / rightleft.ai*
