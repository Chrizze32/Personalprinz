from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QPushButton,
    QLabel,
    QAbstractItemView,
    QMessageBox,
)

from .mitarbeiter import DictTableModel  # wiederverwenden!
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt


class SingleListDialog(QDialog):
    """Dialog zum Bearbeiten einfacher Einspaltenlisten."""

    def __init__(self, title: str, path: Path, colname: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.path = path
        self.colname = colname
        self.model = DictTableModel([colname], path, self)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.resizeColumnsToContents()

        self.btnAdd = QPushButton("Eintrag +")
        self.btnDel = QPushButton("Eintrag −")
        self.btnUp = QPushButton("▲ Hoch")
        self.btnDown = QPushButton("▼ Runter")
        self.btnSave = QPushButton("Speichern")
        self.btnClose = QPushButton("Schließen")

        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"Liste: {self.path.name}"))
        top.addStretch()

        btns = QHBoxLayout()
        btns.addWidget(self.btnAdd)
        btns.addWidget(self.btnDel)
        btns.addWidget(self.btnUp)
        btns.addWidget(self.btnDown)
        btns.addStretch()
        btns.addWidget(self.btnSave)
        btns.addWidget(self.btnClose)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(btns)

        self.btnAdd.clicked.connect(
            lambda: self.model.insertRows(self.model.rowCount(), 1)
        )
        self.btnDel.clicked.connect(self._on_del)
        self.btnUp.clicked.connect(self._on_up)
        self.btnDown.clicked.connect(self._on_down)
        self.btnSave.clicked.connect(self._on_save)
        self.btnClose.clicked.connect(self.accept)

        # Tastaturkürzel: Alt+↑ / Alt+↓
        QShortcut(QKeySequence("Alt+Up"), self, activated=self._on_up)
        QShortcut(QKeySequence("Alt+Down"), self, activated=self._on_down)

    def _on_del(self):
        sel = self.table.selectionModel().selectedRows()
        for ix in sorted(sel, key=lambda i: i.row(), reverse=True):
            self.model.removeRows(ix.row(), 1)

    def _swap_rows(self, r1: int, r2: int) -> None:
        """Hilfsfunktion: vertausche zwei Zeilen im Model und aktualisiere View/Selection."""
        if not (0 <= r1 < self.model.rowCount() and 0 <= r2 < self.model.rowCount()):
            return
        # swap
        self.model.rows[r1], self.model.rows[r2] = (
            self.model.rows[r2],
            self.model.rows[r1],
        )
        self.model.dirty = True
        # betroffene Zeilen neu zeichnen
        top_left = self.model.index(min(r1, r2), 0)
        bottom_right = self.model.index(max(r1, r2), self.model.columnCount() - 1)
        self.model.dataChanged.emit(
            top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole]
        )
        # Auswahl beibehalten
        self.table.clearSelection()
        self.table.selectRow(r2)
        self.table.scrollTo(self.model.index(r2, 0))

    def _on_up(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        if r > 0:
            self._swap_rows(r, r - 1)

    def _on_down(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        if r < self.model.rowCount() - 1:
            self._swap_rows(r, r + 1)

    def _on_save(self):
        try:
            self.model.save()
            QMessageBox.information(
                self, "Gespeichert", f"Datei gespeichert:\n{self.path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))
