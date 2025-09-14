# --- PySide6-Imports für App, Fenster und Widgets
import sys                             # Zugriff auf argv / exit
from PySide6.QtWidgets import (        # GUI-Bausteine
    QApplication, QMainWindow, QWidget, QPushButton,
    QVBoxLayout, QLabel, QToolBar, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt, Slot    # Qt-Konstanten + Slot-Dekorator
from PySide6.QtGui import QAction      # Menü-/Toolbar-Aktionen

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()                         # Basiskonstruktor
        self.setWindowTitle("AfuZ – PySide6 Demo") # Fenstertitel

        # ---- Zentrale Fläche (Central Widget) mit Layout
        central = QWidget(self)                    # Container-Widget
        layout = QVBoxLayout(central)              # Vertikales Layout
        self.label = QLabel("Willkommen 👋")       # Einfache Ausgabe
        self.btn = QPushButton("Zählen")           # Button
        self.count = 0                              # interner Zustand
        layout.addWidget(self.label)               # Widgets ins Layout
        layout.addWidget(self.btn)
        self.setCentralWidget(central)             # als zentrale Fläche setzen

        # ---- Toolbar + Menüaktionen
        toolbar = QToolBar("Hauptleiste", self)    # Toolbar
        self.addToolBar(toolbar)                   # ans Fenster hängen
        act_about = QAction("Info", self)          # Aktion anlegen
        toolbar.addAction(act_about)               # in Toolbar anzeigen

        # ---- Statuszeile
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.statusBar().showMessage("Bereit")     # Text unten links

        # ---- Signals/Slots verbinden (Event → Methode)
        self.btn.clicked.connect(self.on_count)    # Buttonklick
        act_about.triggered.connect(self.on_about) # Menü/Toolbar

        # ---- (Optional) Grund-Style
        self.setMinimumSize(480, 300)              # Fenstergröße
        self.label.setAlignment(Qt.AlignCenter)    # Text mittig

    @Slot()                                        # explizit als Slot markieren
    def on_count(self):
        """Wird bei Buttonklick aufgerufen."""
        self.count += 1                            # Zähler erhöhen
        self.label.setText(f"Zähler: {self.count}")# UI aktualisieren
        self.statusBar().showMessage("Geklickt!")  # kurzes Feedback

    @Slot()
    def on_about(self):
        """Info-Dialog."""
        QMessageBox.information(
            self, "Über AfuZ",
            "AfuZ Demo mit PySide6.\nUI: QMainWindow, Toolbar, Statusbar."
        )

def main():
    app = QApplication(sys.argv)                   # Qt-App erzeugen (genau 1x)
    # Optional: dunkler Look ohne extra Theme-Datei
    app.setStyle("Fusion")
    w = MainWindow()                               # unser Hauptfenster
    w.show()                                       # sichtbar machen
    sys.exit(app.exec())                           # Event-Loop starten

if __name__ == "__main__":
    main()
