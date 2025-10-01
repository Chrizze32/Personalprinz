# gui/mitarbeiter.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict
from datetime import date, timedelta

from PySide6.QtCore import Qt, QModelIndex, QAbstractTableModel, QMimeData
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, QLabel,
    QAbstractItemView, QMessageBox, QLineEdit, QFormLayout, QDialogButtonBox,
    QComboBox, QStyledItemDelegate, QInputDialog
)

from storage import (
    read_csv_rows, write_csv_rows, read_single_column_values,
    MITARBEITER_CSV, MITARBEITER_HEADERS,
    DIENSTGRADE_CSV, TEILEINHEITEN_CSV, ARBEITSZEITMODELLE_CSV,
    ANWESENHEIT_CSV, ANWESENHEIT_HEADERS,
)

# Einheitlicher, gut lesbarer Combo-Style (Feld & Liste identisch)
STYLE_COMBO = """
QComboBox {
    background-color: #f0f0f0;
    color: black;
    border: 1px solid #888;
    padding: 2px 8px 2px 4px;
}
QComboBox QAbstractItemView {
    background-color: #f0f0f0;
    color: black;
    selection-background-color: #0078d7;
    selection-color: white;
    outline: 0;
}
QComboBox::drop-down {
    border-left: 1px solid #888;
    width: 18px;
}
"""

# ------------------------ CSV-Model (generisch) ------------------------

class DictTableModel(QAbstractTableModel):
    """Generisches Tabellenmodell für CSV-Daten (mit optionalem Drag&Drop-Reordering)."""

    def __init__(self, headers: List[str], path: Path, parent=None):
        super().__init__(parent)
        self.headers = list(headers)
        self.path = path
        self.rows: List[List[str]] = []
        self.dirty = False
        self.load()

    # --- Basis QAbstractTableModel ---
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            r, c = index.row(), index.column()
            return self.rows[r][c]
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        r, c = index.row(), index.column()
        self.rows[r][c] = str(value)
        self.dirty = True
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        if not index.isValid():
            # wichtig fürs Reordering per Drop an „leere“ Stellen
            return Qt.ItemIsEnabled | Qt.ItemIsDropEnabled
        # Editierbar + per Drag verschiebbar + Drop möglich
        return base | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        if orientation == Qt.Vertical:
            return section + 1
        return None

    # --- CSV I/O ---
    def load(self):
        self.beginResetModel()
        data = read_csv_rows(self.path)
        self.rows = [[r.get(h, "") for h in self.headers] for r in data]
        self.dirty = False
        self.endResetModel()

    def save(self):
        write_csv_rows(
            self.path,
            [dict(zip(self.headers, row)) for row in self.rows],
            self.headers,
        )
        self.dirty = False

    def insertRows(self, row, count, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row + count - 1)
        for _ in range(count):
            self.rows.insert(row, [""] * len(self.headers))
        self.endInsertRows()
        self.dirty = True
        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if row < 0 or row + count > len(self.rows):
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        for _ in range(count):
            del self.rows[row]
        self.endRemoveRows()
        self.dirty = True
        return True

    # --- Drag & Drop Reordering (ganze Zeilen verschieben) ---
    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return ["application/x-pp-row"]  # einfache eigene Kennung

    def mimeData(self, indexes):
        mime = QMimeData()
        if indexes:
            row = indexes[0].row()
            mime.setData("application/x-pp-row", str(row).encode("utf-8"))
        return mime

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.IgnoreAction:
            return False
        if not data.hasFormat("application/x-pp-row"):
            return False

        source_row = int(bytes(data.data("application/x-pp-row")).decode("utf-8"))
        if row == -1:
            row = parent.row()
            if row == -1:
                row = self.rowCount()

        return self.moveRows(QModelIndex(), source_row, 1, QModelIndex(), row)

    def moveRows(
        self, sourceParent, sourceRow, count, destinationParent, destinationChild
    ):
        if count != 1:
            return False
        if sourceRow < 0 or sourceRow >= len(self.rows):
            return False
        if destinationChild < 0 or destinationChild > len(self.rows):
            return False
        # Kein echter Move (gleiche Position direkt davor/danach)
        if sourceRow == destinationChild or sourceRow + 1 == destinationChild:
            return False

        self.beginMoveRows(
            sourceParent, sourceRow, sourceRow, destinationParent, destinationChild
        )
        row_data = self.rows.pop(sourceRow)
        if destinationChild > sourceRow:
            destinationChild -= 1
        self.rows.insert(destinationChild, row_data)
        self.endMoveRows()
        self.dirty = True
        return True


# ------------------------ Anwesenheit anlegen/löschen ------------------------

def ensure_attendance_span_for_person(pn: str, start: date | None = None, end: date | None = None) -> int:
    """
    Legt Anwesenheitszeilen für PN im Zeitraum [start..end] an (falls nicht vorhanden).
    Standard: heute bis 31.12. des aktuellen Jahres.
    Rückgabe: Anzahl neu angelegter Zeilen.
    """
    if not pn:
        return 0
    today = date.today()
    if start is None:
        start = today
    if end is None:
        end = date(today.year, 12, 31)  # falls ganzes Jahr gewünscht: date(today.year, 1, 1)

    rows = read_csv_rows(ANWESENHEIT_CSV)
    have = {(r.get("Personalnummer","").strip(), r.get("Datum","").strip()) for r in rows}

    added = 0
    one = timedelta(days=1)
    d = start
    while d <= end:
        key = (pn, d.isoformat())
        if key not in have:
            new_row = {h: "" for h in ANWESENHEIT_HEADERS}
            new_row["Personalnummer"] = pn
            new_row["Datum"] = d.isoformat()
            wd = d.weekday()  # 0=Mo..6=So
            new_row["Status"] = "Anwesend" if wd < 5 else "Wochenende"
            rows.append(new_row)
            added += 1
            have.add(key)
        d += one

    if added:
        write_csv_rows(ANWESENHEIT_CSV, rows, ANWESENHEIT_HEADERS)
    return added


def purge_person_from_attendance(pn: str) -> int:
    """
    Entfernt alle Anwesenheitszeilen für PN.
    Rückgabe: Anzahl gelöschter Zeilen.
    """
    if not pn:
        return 0
    rows = read_csv_rows(ANWESENHEIT_CSV)
    before = len(rows)
    rows = [r for r in rows if (r.get("Personalnummer","").strip() != pn)]
    deleted = before - len(rows)
    if deleted:
        write_csv_rows(ANWESENHEIT_CSV, rows, ANWESENHEIT_HEADERS)
    return deleted


# ------------------------ Delegates ------------------------

class ClearOnEditLineDelegate(QStyledItemDelegate):
    """
    LineEdit-Editor, der beim Start leer ist (alter Wert als Placeholder).
    Bei leerem Commit bleibt alter Wert erhalten.
    """
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        cur = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        editor.setPlaceholderText(cur)
        editor.setProperty("old_value", cur)
        editor.setClearButtonEnabled(True)
        return editor

    def setEditorData(self, editor: QLineEdit, index):
        # Start bewusst leer lassen
        editor.setText("")

    def setModelData(self, editor: QLineEdit, model, index):
        old = editor.property("old_value") or ""
        txt = editor.text().strip()
        model.setData(index, txt if txt else old, Qt.EditRole)


class ComboDelegate(QStyledItemDelegate):
    """ComboBox-Delegate mit statischen Werten (einheitlicher Style)."""
    def __init__(self, values: List[str], parent=None):
        super().__init__(parent)
        self.values = list(values)

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(self.values)
        cb.setStyleSheet(STYLE_COMBO)
        return cb

    def setEditorData(self, editor: QComboBox, index):
        cur = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        i = editor.findText(cur)
        if i >= 0:
            editor.setCurrentIndex(i)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)


# ------------------------ Add-Dialog ------------------------

class MitarbeiterAddDialog(QDialog):
    """Popup zum Anlegen eines neuen Mitarbeiters (mit Validierung)."""

    def __init__(self, existing_pns: List[str], az_names: List[str], dg_names: List[str], te_names: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mitarbeiter hinzufügen")
        self._existing = {p.strip() for p in existing_pns}
        self.values: Dict[str, str] = {}

        # Felder
        self.edPN = QLineEdit(); self.edPN.setMaxLength(8); self.edPN.setPlaceholderText("8-stellige Personalnummer")
        self.edNach = QLineEdit(); self.edVor = QLineEdit()

        self.cbAZ = QComboBox(); self.cbDG = QComboBox(); self.cbTE = QComboBox()

        def fill_combo(cb: QComboBox, items: List[str]):
            cb.clear()
            cb.addItem("Bitte auswählen …")
            if items:
                cb.addItems(items)
            else:
                cb.addItem("(Liste ist leer)")
                cb.setEditable(True)  # Tippen erlauben, falls Stammliste noch leer
            cb.setCurrentIndex(0)
            cb.setStyleSheet(STYLE_COMBO)

        fill_combo(self.cbAZ, az_names)
        fill_combo(self.cbDG, dg_names)
        fill_combo(self.cbTE, te_names)

        form = QFormLayout()
        form.addRow("Personalnummer:", self.edPN)
        form.addRow("Nachname:", self.edNach)
        form.addRow("Vorname:", self.edVor)
        form.addRow("Arbeitszeitmodell:", self.cbAZ)
        form.addRow("Dienstgrad:", self.cbDG)
        form.addRow("Teileinheit:", self.cbTE)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)
        self.edPN.setFocus()

    def _normalize_combo_value(self, cb: QComboBox) -> str:
        txt = cb.currentText().strip()
        if txt in ("Bitte auswählen …", "(Liste ist leer)"):
            return ""
        return txt

    def _on_ok(self):
        pn = self.edPN.text().strip()
        if not (len(pn) == 8 and pn.isdigit()):
            QMessageBox.warning(self, "Fehler", "Die Personalnummer muss genau 8 Ziffern haben.")
            return
        if pn in self._existing:
            QMessageBox.warning(self, "Fehler", f"Die Personalnummer {pn} existiert bereits.")
            return

        nach = self.edNach.text().strip()
        vor  = self.edVor.text().strip()
        if not nach or not vor:
            QMessageBox.warning(self, "Fehler", "Bitte Vor- und Nachname angeben.")
            return

        az = self._normalize_combo_value(self.cbAZ)
        dg = self._normalize_combo_value(self.cbDG)
        te = self._normalize_combo_value(self.cbTE)

        self.values = {
            "Personalnummer": pn,
            "Nachname": nach,
            "Vorname": vor,
            "Arbeitszeitmodell": az,
            "Dienstgrad": dg,
            "Teileinheit": te,
        }
        self.accept()


# ------------------------ Hauptdialog ------------------------

class MitarbeiterDialog(QDialog):
    """Editor-Dialog für `Mitarbeiter.csv` mit Add-/Delete-Logik & Dropdowns."""

    COL_PN = 0
    COL_NACH = 1
    COL_VOR = 2
    COL_AZ = 3
    COL_DG = 4
    COL_TE = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mitarbeiter")
        self.model = DictTableModel(MITARBEITER_HEADERS, MITARBEITER_CSV, self)

        # Table
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.resizeColumnsToContents()

        # Delegates: Textspalten „clear on edit“
        text_delegate = ClearOnEditLineDelegate(self.table)
        self.table.setItemDelegateForColumn(self.COL_PN, text_delegate)
        self.table.setItemDelegateForColumn(self.COL_NACH, text_delegate)
        self.table.setItemDelegateForColumn(self.COL_VOR, text_delegate)

        # Delegates: Combos (aus Stammlisten)
        self._refresh_combo_delegates()

        # Buttons
        self.btnReload = QPushButton("Neu laden")
        self.btnAdd = QPushButton("Mitarbeiter hinzufügen")
        self.btnDel = QPushButton("Mitarbeiter löschen")
        self.btnSave = QPushButton("Speichern")
        self.btnClose = QPushButton("Schließen")

        top = QHBoxLayout()
        top.addWidget(QLabel("Tabelle: Mitarbeiter.csv"))
        top.addStretch()

        btns = QHBoxLayout()
        btns.addWidget(self.btnReload)
        btns.addWidget(self.btnAdd)
        btns.addWidget(self.btnDel)
        btns.addStretch()
        btns.addWidget(self.btnSave)
        btns.addWidget(self.btnClose)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(btns)

        # Aktionen
        self.btnReload.clicked.connect(self._on_reload)
        self.btnAdd.clicked.connect(self._on_add)
        self.btnDel.clicked.connect(self._on_delete)
        self.btnSave.clicked.connect(self._on_save)
        self.btnClose.clicked.connect(self.accept)

        # Tastaturkürzel (optional)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self._move_up)
        QShortcut(QKeySequence("Alt+Down"), self, activated=self._move_down)

    # ---------- Stammlisten / Delegates ----------
    def _get_lists(self) -> tuple[List[str], List[str], List[str]]:
        az = [ (r.get("Modell","") or "").strip() for r in read_csv_rows(ARBEITSZEITMODELLE_CSV) ]
        az = [x for x in az if x]
        dg = read_single_column_values(DIENSTGRADE_CSV, "Dienstgrad")
        te = read_single_column_values(TEILEINHEITEN_CSV, "Teileinheit")
        return az, dg, te

    def _refresh_combo_delegates(self):
        az, dg, te = self._get_lists()
        az_values = [""] + az
        dg_values = [""] + dg
        te_values = [""] + te
        self.table.setItemDelegateForColumn(self.COL_AZ, ComboDelegate(az_values, self.table))
        self.table.setItemDelegateForColumn(self.COL_DG, ComboDelegate(dg_values, self.table))
        self.table.setItemDelegateForColumn(self.COL_TE, ComboDelegate(te_values, self.table))

    # ---------- Button-Handler ----------
    def _on_reload(self):
        self.model.load()
        self._refresh_combo_delegates()
        self.table.resizeColumnsToContents()

    def _on_add(self):
        existing_pn = [(row[self.COL_PN] or "").strip() for row in self.model.rows]
        az, dg, te = self._get_lists()
        dlg = MitarbeiterAddDialog(existing_pn, az, dg, te, self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values

        # neue Zeile einfügen
        self.model.insertRows(self.model.rowCount(), 1)
        r = self.model.rowCount() - 1
        for col, key in [
            (self.COL_PN, "Personalnummer"),
            (self.COL_NACH, "Nachname"),
            (self.COL_VOR, "Vorname"),
            (self.COL_AZ, "Arbeitszeitmodell"),
            (self.COL_DG, "Dienstgrad"),
            (self.COL_TE, "Teileinheit"),
        ]:
            self.model.setData(self.model.index(r, col), vals.get(key, ""), Qt.EditRole)

        # speichern
        try:
            self.model.save()
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")
            return

        # Anwesenheit vorbereiten (heute..31.12.)
        pn = vals.get("Personalnummer", "")
        try:
            _ = ensure_attendance_span_for_person(pn)
        except Exception as e:
            QMessageBox.warning(self, "Hinweis", f"Anwesenheit konnte nicht vorbereitet werden:\n{e}")

        self.table.selectRow(r)
        self.table.scrollToBottom()

    def _on_delete(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        pn = (self.model.rows[r][self.COL_PN] or "").strip()
        name = f"{self.model.rows[r][self.COL_VOR]} {self.model.rows[r][self.COL_NACH]}".strip()

        text, ok = QInputDialog.getText(
            self,
            "Löschen bestätigen",
            f"Sind Sie sich sicher, dass Sie den Nutzer „{name or pn or 'unbekannt'}“ löschen wollen?\n\n"
            "Bitte geben Sie zum Bestätigen „löschen“ ein:"
        )
        if not ok or (text or "").strip().lower() != "löschen":
            return

        # Anwesenheit purgen
        try:
            deleted = purge_person_from_attendance(pn)
        except Exception as e:
            QMessageBox.warning(self, "Hinweis", f"Anwesenheits-Datensätze konnten nicht vollständig entfernt werden:\n{e}")
            deleted = 0

        # Mitarbeiter-Zeile entfernen & speichern
        self.model.removeRows(r, 1)
        try:
            self.model.save()
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")
            return

        QMessageBox.information(self, "Gelöscht", f"Mitarbeiter gelöscht.\nEntfernte Anwesenheitszeilen: {deleted}")

    def _on_save(self):
        # PN-Validierung (8-stellig, eindeutig)
        pns = []
        for i, row in enumerate(self.model.rows):
            pn = (row[self.COL_PN] or "").strip()
            if not (len(pn) == 8 and pn.isdigit()):
                QMessageBox.warning(self, "Fehler", f"Zeile {i+1}: Personalnummer muss 8-stellig sein.")
                return
            if pn in pns:
                QMessageBox.warning(self, "Fehler", f"Zeile {i+1}: Personalnummer {pn} ist nicht eindeutig.")
                return
            pns.append(pn)

        try:
            self.model.save()
            QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{MITARBEITER_CSV}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))

    # Optional: Move via Shortcut (Alternativ zu Drag&Drop)
    def _move_up(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        if r <= 0:
            return
        self.model.rows[r-1], self.model.rows[r] = self.model.rows[r], self.model.rows[r-1]
        self.model.dirty = True
        self.model.dataChanged.emit(self.model.index(r-1, 0), self.model.index(r, self.model.columnCount()-1),
                                    [Qt.DisplayRole, Qt.EditRole])
        self.table.selectRow(r-1)

    def _move_down(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        if r >= self.model.rowCount() - 1:
            return
        self.model.rows[r+1], self.model.rows[r] = self.model.rows[r], self.model.rows[r+1]
        self.model.dirty = True
        self.model.dataChanged.emit(self.model.index(r, 0), self.model.index(r+1, self.model.columnCount()-1),
                                    [Qt.DisplayRole, Qt.EditRole])
        self.table.selectRow(r+1)
