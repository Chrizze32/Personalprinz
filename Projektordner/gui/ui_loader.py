# gui/ui_loader.py
"""
UI-Finder & Loader für PersonalPrinz (PySide6).
Hält main.py schlank und kapselt Fehlermeldungen sauber.
"""

from __future__ import annotations
from pathlib import Path
import os

SCRIPT_DIR = Path(__file__).resolve().parent.parent  # Projektordner
UI_DIR = SCRIPT_DIR / "ui"
UI_CANDIDATES = ["MainWindow.ui", "mainwindow.ui", "personalprinz.ui"]


def find_ui_file() -> Path:
    """Finde eine passende *.ui-Datei im Projekt- oder ./ui/ Ordner, oder via PP_UI_FILE."""
    env = os.getenv("PP_UI_FILE")
    if env:
        p = Path(env)
        if not p.is_absolute():
            # zuerst Projektordner, dann ./ui
            p = (SCRIPT_DIR / env) if (SCRIPT_DIR / env).exists() else (UI_DIR / env)
        if p.exists():
            return p

    for base in (SCRIPT_DIR, UI_DIR):
        for name in UI_CANDIDATES:
            p = base / name
            if p.exists():
                return p
    raise FileNotFoundError(
        "Keine UI-Datei gefunden. Lege MainWindow.ui im Projektordner oder im Unterordner ./ui ab "
        "(oder setze PP_UI_FILE)."
    )


def load_ui_mainwindow(ui_path: Path):
    """Lade die MainWindow-UI mit QUiLoader und prüfe die Kern-Buttons."""
    from PySide6.QtCore import QFile
    from PySide6.QtUiTools import QUiLoader
    from PySide6.QtWidgets import QWidget, QPushButton

    loader = QUiLoader()
    f = QFile(str(ui_path))
    if not f.open(QFile.ReadOnly):
        raise RuntimeError(f"Konnte UI nicht öffnen: {ui_path}")
    win: QWidget = loader.load(f)
    f.close()

    # Stelle sicher, dass die erwarteten Buttons existieren:
    needed = {
        "btnEdit_2": QPushButton,  # Personal
        "btnEdit_3": QPushButton,  # Anwesenheit
        "btnEdit_5": QPushButton,  # Dienstgrade
        "btnEdit_6": QPushButton,  # Teileinheiten
    }
    for obj, cls in needed.items():
        w = win.findChild(cls, obj)
        if w is None:
            raise RuntimeError(f"Button '{obj}' wurde in der UI nicht gefunden.")
        setattr(win, obj, w)

    return win
