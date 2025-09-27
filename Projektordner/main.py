"""
GUI-Starter für PersonalPrinz (PySide6).

- Lädt die .ui-Datei (MainWindow) via gui.ui_loader.
- Verdrahtet Buttons mit Dialogen aus gui.dialogs.
- Nutzt Storage/CSV-Helfer aus storage.py.

Start:
    python ./main.py
"""

from __future__ import annotations

import os
import sys

from gui.ui_loader import find_ui_file, load_ui_mainwindow
from gui.dialogs.mitarbeiter import MitarbeiterDialog
from gui.dialogs.attendance import AttendanceDialog
from gui.dialogs.single_list import SingleListDialog

from storage import (
    DIENSTGRADE_CSV,
    TEILEINHEITEN_CSV,
    ensure_all_csvs,
)


def run_gui() -> int:
    """Starte die Qt-GUI (PySide6) und verdrahte die Dialoge."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)

    try:
        ui_file = find_ui_file()
        win = load_ui_mainwindow(ui_file)
    except Exception as e:
        QMessageBox.critical(None, "Fehler beim Laden der UI", str(e))
        return 1

    # Buttons verdrahten
    try:
        win.btnEdit_2.clicked.connect(lambda: MitarbeiterDialog(win).exec())  # Personal
        win.btnEdit_3.clicked.connect(
            lambda: AttendanceDialog(win).exec()
        )  # Anwesenheit
        win.btnEdit_5.clicked.connect(  # Dienstgrade
            lambda: SingleListDialog(
                "Dienstgrade bearbeiten", DIENSTGRADE_CSV, "Dienstgrad", win
            ).exec()
        )
        win.btnEdit_6.clicked.connect(  # Teileinheiten
            lambda: SingleListDialog(
                "Teileinheiten bearbeiten", TEILEINHEITEN_CSV, "Teileinheit", win
            ).exec()
        )
    except Exception as e:
        QMessageBox.critical(None, "Fehler beim Verdrahten der Buttons", str(e))
        return 1

    win.show()
    return app.exec()


def main() -> int:
    """Startpunkt: CSVs anlegen und (falls nicht headless) die GUI starten."""
    ensure_all_csvs()
    if os.environ.get("PP_HEADLESS", "0") == "1":
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
