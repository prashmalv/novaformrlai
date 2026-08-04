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
    
    
#   ---------------------------# Samarth code Start Here -------------------------------------
    
    # ── Login/Main Window Loop ────────────────────────────────────────────────
    while True:
        login = LoginDialog()
        if login.exec() != LoginDialog.DialogCode.Accepted:
            break

        user = login.authenticated_user

        log_action(
            user["username"],
            user["full_name"],
            "LOGIN",
            f"Host: {socket.gethostname()}"
        )

        try:
            window = MainWindow(current_user=user)

            logged_out = False

            def on_logout():
                nonlocal logged_out
                logged_out = True
                window.close()

            window.logout_requested.connect(on_logout)

            window.show()
            window.raise_()
            window.activateWindow()

            app.exec()

            if not logged_out:
                break

        except Exception as _exc:
            import traceback
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                None,
                "Startup Error",
                f"NovoForm failed to start:\n\n{_exc}\n\n"
                + traceback.format_exc()
            )
            sys.exit(1)

    sys.exit(0)


#   ---------------------------# Samarth code End Here -------------------------------------


# This is exiting code of prashant sir only I change where self.close() after login i place login screen only


    # # ── Login gate ────────────────────────────────────────────────────────────
    # login = LoginDialog()
    # if login.exec() != LoginDialog.DialogCode.Accepted:
    #     sys.exit(0)

    # user = login.authenticated_user
    # log_action(user["username"], user["full_name"], "LOGIN",
    #            f"Host: {socket.gethostname()}")

    # # ── Main window ───────────────────────────────────────────────────────────
    # try:
    #     window = MainWindow(current_user=user)
    #     window.show()
    #     # On macOS the frameless login dialog leaves the app with no focused window
    #     # briefly; raise_() + activateWindow() ensures the main window comes to front.
    #     window.raise_()
    #     window.activateWindow()
    # except Exception as _exc:
    #     import traceback
    #     from PyQt6.QtWidgets import QMessageBox
    #     QMessageBox.critical(
    #         None, "Startup Error",
    #         f"NovoForm failed to start:\n\n{_exc}\n\n"
    #         + traceback.format_exc()
    #     )
    #     sys.exit(1)

    # exit_code = app.exec()
    # log_action(user["username"], user["full_name"], "LOGOUT", "Application closed")
    # sys.exit(exit_code)


if __name__ == "__main__":
    main()
