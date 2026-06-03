"""
NovoForm — Login Dialog
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap

from src.auth.auth_manager import authenticate, initialize_db

_LOGO = Path(__file__).parent.parent.parent / "assets" / "images" / "NovaLogo.png"

_NOVA_BLUE   = "#1a3a5c"
_NOVA_ACCENT = "#2c5f8a"
_WHITE       = "#ffffff"
_LIGHT_BG    = "#f4f7fb"
_ERR_RED     = "#c0392b"
_HINT_GRAY   = "#6c757d"


class LoginDialog(QDialog):
    """
    Shown before MainWindow.  Sets self.authenticated_user on success.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        initialize_db()
        self.authenticated_user = None
        self._build_ui()
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setFixedWidth(420)
        self.setMinimumHeight(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Card frame
        card = QFrame()
        card.setObjectName("loginCard")
        card.setStyleSheet(f"""
            QFrame#loginCard {{
                background: {_WHITE};
                border-radius: 12px;
                border: 1px solid #d0dce8;
            }}
        """)
        root.addWidget(card)

        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(0, 0, 0, 24)
        vlay.setSpacing(0)

        # ── Header bar ──────────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(90)
        header.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_NOVA_BLUE}, stop:1 {_NOVA_ACCENT});
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(20, 0, 20, 0)

        # Logo
        if _LOGO.exists():
            logo_lbl = QLabel()
            px = QPixmap(str(_LOGO)).scaledToHeight(
                52, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(px)
            hlay.addWidget(logo_lbl)
            hlay.addSpacing(14)

        # Title
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t1 = QLabel("NovoForm")
        t1.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t1.setStyleSheet(f"color:{_WHITE}; background:transparent;")
        t2 = QLabel("Formwork BOQ Generator")
        t2.setFont(QFont("Segoe UI", 9))
        t2.setStyleSheet(f"color:rgba(255,255,255,0.75); background:transparent;")
        title_col.addWidget(t1)
        title_col.addWidget(t2)
        hlay.addLayout(title_col)
        hlay.addStretch()

        vlay.addWidget(header)
        vlay.addSpacing(28)

        # ── Form area ───────────────────────────────────────────────────────
        form_wrap = QVBoxLayout()
        form_wrap.setContentsMargins(36, 0, 36, 0)
        form_wrap.setSpacing(0)

        signin_lbl = QLabel("Sign In")
        signin_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        signin_lbl.setStyleSheet(f"color:{_NOVA_BLUE};")
        form_wrap.addWidget(signin_lbl)
        form_wrap.addSpacing(4)

        sub_lbl = QLabel("Enter your credentials to continue")
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet(f"color:{_HINT_GRAY};")
        form_wrap.addWidget(sub_lbl)
        form_wrap.addSpacing(22)

        # Username
        user_lbl = QLabel("Username")
        user_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        user_lbl.setStyleSheet(f"color:{_NOVA_BLUE};")
        form_wrap.addWidget(user_lbl)
        form_wrap.addSpacing(4)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("Enter username")
        self._user_edit.setFixedHeight(40)
        self._user_edit.setStyleSheet(self._field_style())
        form_wrap.addWidget(self._user_edit)
        form_wrap.addSpacing(14)

        # Password
        pw_lbl = QLabel("Password")
        pw_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        pw_lbl.setStyleSheet(f"color:{_NOVA_BLUE};")
        form_wrap.addWidget(pw_lbl)
        form_wrap.addSpacing(4)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)
        self._pw_edit = QLineEdit()
        self._pw_edit.setPlaceholderText("Enter password")
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setFixedHeight(40)
        self._pw_edit.setStyleSheet(self._field_style())
        pw_row.addWidget(self._pw_edit)
        form_wrap.addLayout(pw_row)

        show_pw = QCheckBox("Show password")
        show_pw.setStyleSheet(f"color:{_HINT_GRAY}; font-size:9pt;")
        show_pw.toggled.connect(
            lambda on: self._pw_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on
                else QLineEdit.EchoMode.Password))
        form_wrap.addSpacing(6)
        form_wrap.addWidget(show_pw)
        form_wrap.addSpacing(8)

        # Error label
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet(
            f"color:{_ERR_RED}; font-size:9pt; font-weight:600;")
        self._err_lbl.setWordWrap(True)
        self._err_lbl.setFixedHeight(18)
        form_wrap.addWidget(self._err_lbl)
        form_wrap.addSpacing(14)

        # Login button
        self._login_btn = QPushButton("Login")
        self._login_btn.setFixedHeight(42)
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_NOVA_BLUE};
                color: {_WHITE};
                border-radius: 6px;
                font-size: 11pt;
                font-weight: 700;
                border: none;
            }}
            QPushButton:hover  {{ background: {_NOVA_ACCENT}; }}
            QPushButton:pressed{{ background: #122a45; }}
        """)
        self._login_btn.clicked.connect(self._do_login)
        form_wrap.addWidget(self._login_btn)

        vlay.addLayout(form_wrap)
        vlay.addStretch()

        # ── Footer ──────────────────────────────────────────────────────────
        footer_lbl = QLabel(
            "Nova Formworks Pvt. Ltd. · NovoForm v1.1 · "
            "Default admin: admin / nova@123"
        )
        footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_lbl.setStyleSheet(f"color:{_HINT_GRAY}; font-size:8pt;")
        footer_lbl.setWordWrap(True)
        footer_lbl.setContentsMargins(36, 0, 36, 0)
        vlay.addWidget(footer_lbl)

        # Enter key → login
        self._pw_edit.returnPressed.connect(self._do_login)
        self._user_edit.returnPressed.connect(self._pw_edit.setFocus)

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _do_login(self):
        username = self._user_edit.text().strip()
        password = self._pw_edit.text()

        if not username or not password:
            self._err_lbl.setText("Please enter username and password.")
            return

        user = authenticate(username, password)
        if user is None:
            self._err_lbl.setText("Invalid username or password.")
            self._pw_edit.clear()
            self._pw_edit.setFocus()
            return

        self.authenticated_user = user
        self.accept()

    @staticmethod
    def _field_style() -> str:
        return """
            QLineEdit {
                border: 1.5px solid #c8d8e8;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 10pt;
                background: #f9fbfd;
                color: #1a3a5c;
            }
            QLineEdit:focus {
                border-color: #2c5f8a;
                background: white;
            }
        """
