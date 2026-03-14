"""
NovoForm — Formwork Analysis & BOQ Generator
Phase 1 Demo Entry Point
"""
import sys
import os

# Ensure src is on path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from src.ui.main_window import MainWindow


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

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
