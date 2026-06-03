"""
NovoForm — Formwork Analysis & BOQ Generator
Phase 1 Demo Entry Point
"""
import sys
import os

# Ensure src is on path
sys.path.insert(0, os.path.dirname(__file__))

import socket
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from src.ui.main_window import MainWindow
from src.ui.login_dialog import LoginDialog
from src.auth.auth_manager import log_action


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NovoForm")
    app.setOrganizationName("Nova Formworks Pvt. Ltd.")

    # Global font (cross-platform: Segoe UI on Windows, SF Pro/system on Mac)
    from PyQt6.QtGui import QFontDatabase
    preferred = [".AppleSystemUIFont", "Helvetica Neue", "Segoe UI", "Arial"]
    chosen = next((f for f in preferred if f in QFontDatabase.families()), "")
    font = QFont(chosen if chosen else QFont().family(), 10)
    app.setFont(font)

    # ── Login gate ────────────────────────────────────────────────────────────
    login = LoginDialog()
    if login.exec() != LoginDialog.DialogCode.Accepted:
        sys.exit(0)

    user = login.authenticated_user
    log_action(user["username"], user["full_name"], "LOGIN",
               f"Host: {socket.gethostname()}")

    # ── Main window ───────────────────────────────────────────────────────────
    window = MainWindow(current_user=user)
    window.show()

    exit_code = app.exec()
    log_action(user["username"], user["full_name"], "LOGOUT", "Application closed")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
