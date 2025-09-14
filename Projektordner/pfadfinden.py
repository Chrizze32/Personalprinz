import os
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

base = os.path.dirname(__file__)  # Ordner, wo dein Skript liegt
ui_file = os.path.join(base, "ui", "mainwindow.ui")

f = QFile(ui_file)
if not f.exists():
    raise FileNotFoundError(f"UI-Datei nicht gefunden: {ui_file}")

f.open(QFile.ReadOnly)
window = QUiLoader().load(f)
f.close()