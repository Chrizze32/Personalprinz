# gui/mitarbeiter.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterable, Tuple

from PySide6.QtCore import Qt, QModelIndex, QAbstractTableModel
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView,
    QPushButton, QLabel, QAbstractItemView, QMessageBox,
    QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QStyledItemDelegate, QWidget, QInputDialog
)

from storage import (
    read_csv_rows,
    write_csv_rows,
    MITARBEITER_CSV,
    MITARBEITER_HEADERS,
    DIENSTGRADE_CSV,
    TEILEINHEITEN_CSV,
    ANWESENHEIT_CSV,
    ANWESENHEIT_HEADERS,
)

# ----------------- Utilities -----------------

def _read_single_column_values(path: Path) -> List[str]:
    """Liest eine Einspalten-CSV (SingleList) und gibt eindeutige, nicht-leere, sortierte Werte zurück."""
    try:
        rows = read_csv_rows(path)
    except Exception:
        return []
    vals = []
    for r in rows:
        if not r:
            continue
        vals.append(next(iter(r.values()), "") or "")
    return sorted({v.strip() for v in vals if v and v.strip()})

def _collect_arbeitszeitmodelle() -> List[str]:
    """Leitet vorhandene Arbeitszeitmodelle aus Mitarbeiter.csv ab (unique, sortiert)."""
    try:
        rows = read_csv_rows(MITARBEITER_CSV)
    except Exception:
        return []
    azm_key = None
    candidates = ["Arbeitszeitmodell", "Arbeitszeit", "AZ", "AZ-Modell"]
    for k in MITARBEITER_HEADERS:
        if k in candidates:
            azm_key = k
            break
    if azm_key is None:
        for k in MITARBEITER_HEADERS:
            if "arbeit" in k.lower():
                azm_key = k
                break
    if azm_key is None:
        return []
    vals = [(r.get(azm_key) or "").strip() for r in rows]
    return sorted({v for v in vals if v})

def _idx(headers: List[str], name: str) -> Optional[int]:
    try:
        return headers.index(name)
    except ValueError:
        return None

def _delete_attendance_for_pn(pn: str) -> int:
    """Löscht alle Anwesenheitszeilen mit gegebener PN. Rückgabe: Anzahl gelöschter Zeilen."""
    rows = read_csv_rows(ANWESENHEIT_CSV)
    before = len(rows)
    rows = [r for r in rows if (r.get("Personalnummer") or "").strip() != pn]
    if len(rows) != before:
        write_csv_rows(ANWESENHEIT_CSV, rows, ANWESENHEIT_HEADERS)
    return before - len(rows)

# ----------------- Model -----------------

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
        from PySide6.QtCore import QMimeData
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


# ----------------- Combobox-Delegate -----------------

class ComboDelegate(QStyledItemDelegate):
    """
    Stellt für bestimmte Spalten eine ComboBox als Editor bereit.
    - items: Liste der Auswahlwerte
    - editable: True -> Nutzer kann auch freien Text eingeben (z. B. Arbeitszeitmodell)
    """
    def __init__(self, items: Iterable[str], editable: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items = list(items)
        self._editable = editable

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(self._items)
        cb.setEditable(self._editable)
        cb.setInsertPolicy(QComboBox.NoInsert)
        return cb

    def setEditorData(self, editor: QComboBox, index):
        val = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        i = editor.findText(val)
        if i >= 0:
            editor.setCurrentIndex(i)
        else:
            if self._editable and val:
                editor.setEditText(val)

    def setModelData(self, editor: QComboBox, model, index):
        val = editor.currentText().strip()
        model.setData(index, val, Qt.EditRole)


class ClearOnEditDelegate(QStyledItemDelegate):
    """
    Ein Delegate, das beim Starten des Editors den bestehenden Text leert,
    sodass der Nutzer direkt „frisch“ eintippen kann.
    """

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(self._items)
        cb.setEditable(self._editable)
        cb.setInsertPolicy(QComboBox.NoInsert)

        # Hintergrund setzen, damit nichts durchscheint
        cb.setStyleSheet("QComboBox { background-color: white; }"
                         "QAbstractItemView { background-color: white; }")

        return cb


# ----------------- Add-Dialog -----------------

class MitarbeiterAddDialog(QDialog):
    """
    Formular zum Hinzufügen eines Mitarbeiters.
    Nutzt Single-Listen (Dienstgrade, Teileinheiten) und lernt AZ-Modelle aus Daten.
    Prüft PN: genau 8-stellig & eindeutig.
    """
    def __init__(self, headers: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mitarbeiter hinzufügen")
        self.headers = headers
        self.values: Dict[str, str] = {}

        # Dropdown-Quellen
        dienstgrade = _read_single_column_values(DIENSTGRADE_CSV)
        teileinheiten = _read_single_column_values(TEILEINHEITEN_CSV)
        az_modelle = _collect_arbeitszeitmodelle()

        # heuristische Feld-Erkennung
        idx_pn = _idx(headers, "Personalnummer") or _idx(headers, "PN")
        idx_name = None
        for candidate in ("Name", "Nachname"):
            idx_name = _idx(headers, candidate) if idx_name is None else idx_name
        idx_vorname = _idx(headers, "Vorname")
        idx_dienstgrad = _idx(headers, "Dienstgrad")
        idx_te = _idx(headers, "Teileinheit")
        idx_az = None
        for i, h in enumerate(headers):
            if "arbeit" in h.lower():
                idx_az = i
                break

        form = QFormLayout()
        self.inputs: Dict[str, QWidget] = {}

        def add_lineedit(label: str):
            w = QLineEdit()
            form.addRow(label + ":", w)
            self.inputs[label] = w

        def add_combo(label: str, items: List[str], editable=False):
            w = QComboBox()
            w.addItems(items)
            w.setEditable(editable)
            form.addRow(label + ":", w)
            self.inputs[label] = w

        # Reihenfolge: PN, Vorname, Name, Dienstgrad, Teileinheit, Arbeitszeitmodell, (Rest frei)
        used = set()
        if idx_pn is not None:
            add_lineedit(headers[idx_pn]); used.add(headers[idx_pn])
        if idx_vorname is not None:
            add_lineedit(headers[idx_vorname]); used.add(headers[idx_vorname])
        if idx_name is not None:
            add_lineedit(headers[idx_name]); used.add(headers[idx_name])

        if idx_dienstgrad is not None:
            add_combo(headers[idx_dienstgrad], dienstgrade or [], editable=False)
            used.add(headers[idx_dienstgrad])
        if idx_te is not None:
            add_combo(headers[idx_te], teileinheiten or [], editable=False)
            used.add(headers[idx_te])
        if idx_az is not None:
            add_combo(headers[idx_az], az_modelle or [], editable=True)
            used.add(headers[idx_az])

        for h in headers:
            if h in used:
                continue
            add_lineedit(h)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

        # Fokus auf PN, wenn vorhanden
        if idx_pn is not None:
            try:
                self.inputs[headers[idx_pn]].setFocus()
            except Exception:
                pass

    def _on_accept(self):
        # alle Werte einsammeln in Header-Reihenfolge
        vals: Dict[str, str] = {}
        for h, w in self.inputs.items():
            if isinstance(w, QLineEdit):
                vals[h] = w.text().strip()
            elif isinstance(w, QComboBox):
                vals[h] = w.currentText().strip()
            else:
                vals[h] = ""

        # --- Validierung Personalnummer ---
        pn = vals.get("Personalnummer", "") or vals.get("PN", "")
        if not pn:
            QMessageBox.warning(self, "Fehler", "Bitte eine Personalnummer angeben.")
            return
        if not (pn.isdigit() and len(pn) == 8):
            QMessageBox.warning(self, "Fehler", "Die Personalnummer muss genau 8 Ziffern haben.")
            return

        # Prüfen, ob PN bereits existiert
        existing = {(r.get("Personalnummer") or "").strip() for r in read_csv_rows(MITARBEITER_CSV)}
        if pn in existing:
            QMessageBox.warning(self, "Fehler", f"Die Personalnummer {pn} existiert bereits.")
            return

        self.values = vals
        self.accept()

# ----------------- Hauptdialog -----------------

class MitarbeiterDialog(QDialog):
    """Editor-Dialog für `Mitarbeiter.csv` mit Add-Form, Dropdown-Editing und sicherem Löschen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mitarbeiter")
        self.model = DictTableModel(MITARBEITER_HEADERS, MITARBEITER_CSV, self)

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

        # --- Dropdown-Delegates für bestimmte Spalten ---
        # Dienstgrad
        col_dg = _idx(self.model.headers, "Dienstgrad")
        dg_vals = _read_single_column_values(DIENSTGRADE_CSV)
        if col_dg is not None and dg_vals:
            self.table.setItemDelegateForColumn(col_dg, ComboDelegate(dg_vals, editable=False, parent=self.table))

        # Teileinheit
        col_te = _idx(self.model.headers, "Teileinheit")
        te_vals = _read_single_column_values(TEILEINHEITEN_CSV)
        if col_te is not None and te_vals:
            self.table.setItemDelegateForColumn(col_te, ComboDelegate(te_vals, editable=False, parent=self.table))

        # Arbeitszeitmodell (aus Daten gelernt + frei editierbar)
        col_az = None
        for i, h in enumerate(self.model.headers):
            if "arbeit" in h.lower():
                col_az = i
                break
        az_vals = _collect_arbeitszeitmodelle()
        if col_az is not None:
            self.table.setItemDelegateForColumn(col_az, ComboDelegate(az_vals, editable=True, parent=self.table))

        # --- Buttons (ohne Zeile + / Zeile −) ---
        self.btnReload = QPushButton("Neu laden")
        self.btnAddPerson = QPushButton("Mitarbeiter hinzufügen")
        self.btnDeletePerson = QPushButton("Mitarbeiter löschen")  # NEU
        self.btnSave = QPushButton("Speichern")
        self.btnClose = QPushButton("Schließen")

        top = QHBoxLayout()
        top.addWidget(QLabel("Tabelle: Mitarbeiter.csv"))
        top.addStretch()

        btns = QHBoxLayout()
        btns.addWidget(self.btnReload)
        btns.addWidget(self.btnAddPerson)
        btns.addWidget(self.btnDeletePerson)  # NEU
        btns.addStretch()
        btns.addWidget(self.btnSave)
        btns.addWidget(self.btnClose)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(btns)

        # --- Wiring ---
        self.btnReload.clicked.connect(
            lambda: (self.model.load(), self.table.resizeColumnsToContents())
        )
        self.btnAddPerson.clicked.connect(self._on_add_person)
        self.btnDeletePerson.clicked.connect(self._on_delete_person)  # NEU
        self.btnSave.clicked.connect(self._on_save)
        self.btnClose.clicked.connect(self.accept)

    # ------- Slots -------

    def _on_add_person(self):
        dlg = MitarbeiterAddDialog(self.model.headers, self)
        if dlg.exec() != QDialog.Accepted:
            return
        # neue Zeile ans Ende
        row = [dlg.values.get(h, "") for h in self.model.headers]
        self.model.insertRows(self.model.rowCount(), 1)
        r = self.model.rowCount() - 1
        for c, val in enumerate(row):
            self.model.setData(self.model.index(r, c), val, Qt.EditRole)
        self.table.selectRow(r)
        self.table.scrollToBottom()

    def _on_delete_person(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Hinweis", "Bitte zunächst eine Zeile auswählen.")
            return

        r = sel[0].row()
        # PN ermitteln
        try:
            col_pn = self.model.headers.index("Personalnummer")
            pn = (self.model.rows[r][col_pn] or "").strip()
        except Exception:
            pn = ""

        if not pn:
            QMessageBox.warning(self, "Achtung", "In der ausgewählten Zeile fehlt die Personalnummer – Abbruch.")
            return

        # Sicherheitsabfrage
        text, ok = QInputDialog.getText(
            self,
            "Sicher löschen?",
            (
                f"Du bist dabei, den Mitarbeiter mit PN {pn} zu löschen.\n"
                "Dabei werden auch ALLE Einträge dieser PN aus der Anwesenheit gelöscht.\n\n"
                "Zur Bestätigung tippe bitte genau: löschen"
            ),
        )
        if not ok or text.strip() != "löschen":
            QMessageBox.information(self, "Abgebrochen", "Löschen wurde abgebrochen.")
            return

        # Anwesenheit löschen
        removed = _delete_attendance_for_pn(pn)

        # Mitarbeiter-Zeile löschen
        if not self.model.removeRows(r, 1):
            QMessageBox.critical(self, "Fehler", "Mitarbeiter konnte nicht aus der Tabelle entfernt werden.")
            return

        QMessageBox.information(
            self,
            "Gelöscht",
            f"Mitarbeiter (PN {pn}) gelöscht.\nEntfernte Anwesenheitszeilen: {removed}"
        )

    def _on_save(self):
        try:
            self.model.save()
            QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{MITARBEITER_CSV}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))
