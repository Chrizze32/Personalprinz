"""
GUI-Starter für PersonalPrinz (PySide6).

- Lädt eine .ui-Datei (MainWindow) via QUiLoader.
- Verdrahtet Buttons mit Dialogen.
- Nutzt Logik aus logic.py.

Start:
    python .\\main.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from logic import (
    # Pfade & Header
    MITARBEITER_CSV,
    DIENSTGRADE_CSV,
    TEILEINHEITEN_CSV,
    ANWESENHEIT_CSV,
    MITARBEITER_HEADERS,
    ANWESENHEIT_HEADERS,
    # Logikfunktionen
    ensure_all_csvs,
    read_csv_rows,
    write_csv_rows,
    read_single_column_values,
    write_single_column_values,
    generate_attendance_for_person,
    remove_attendance_for_person,
)

# ---------- UI-Datei finden ----------
SCRIPT_DIR = Path(__file__).resolve().parent
UI_DIR = SCRIPT_DIR / "ui"
UI_CANDIDATES = ["MainWindow.ui", "mainwindow.ui", "personalprinz.ui"]


def find_ui_file() -> Path:
    """
    Finde die UI-Datei für das Hauptfenster.

    Reihenfolge:
      1) Umgebungsvariable PP_UI_FILE
      2) Projektordner
      3) ./ui

    Returns:
        Pfad zur .ui-Datei.

    Raises:
        FileNotFoundError: Wenn keine passende Datei gefunden wird.
    """
    env = os.getenv("PP_UI_FILE")
    if env:
        p = Path(env)
        if not p.is_absolute():
            if (SCRIPT_DIR / env).exists():
                p = SCRIPT_DIR / env
            else:
                p = UI_DIR / env
        if p.exists():
            return p

    for base in (SCRIPT_DIR, UI_DIR):
        for name in UI_CANDIDATES:
            p = base / name
            if p.exists():
                return p

    raise FileNotFoundError(
        "Keine UI-Datei gefunden. Lege MainWindow.ui im Projektordner oder ./ui ab."
    )


# ---------- GUI (alle PySide6-Imports lokal!) ----------
def run_gui() -> int:
    """
    Starte die Qt-GUI (PySide6) und verdrahte die Dialoge.

    Wichtig: Alle Qt-Imports & GUI-Klassen sind **lokal** in dieser Funktion,
    damit Import/Tests ohne PySide6 funktionieren.
    """
    from PySide6.QtCore import Qt, QModelIndex, QFile, QRegularExpression, QAbstractTableModel
    from PySide6.QtGui import QKeySequence, QShortcut, QRegularExpressionValidator
    from PySide6.QtWidgets import (
        QApplication,
        QMessageBox,
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QTableView,
        QPushButton,
        QLabel,
        QLineEdit,
        QComboBox,
        QStyledItemDelegate,
        QAbstractItemView,
        QWidget,
        QPushButton as _QPushButton,
    )
    from PySide6.QtUiTools import QUiLoader

    ui_file = find_ui_file()

    # ===== Delegates =====
    class ComboBoxDelegate(QStyledItemDelegate):
        """Delegate mit Auswahlliste für Tabellenzellen."""

        def __init__(self, items, parent=None):
            super().__init__(parent)
            self.items = list(items)

        def createEditor(self, parent, option, index):
            cb = QComboBox(parent)
            cb.addItems(self.items)
            return cb

        def setEditorData(self, editor, index):
            val = index.data() or ""
            i = editor.findText(val)
            editor.setCurrentIndex(max(i, 0))

        def setModelData(self, editor, model, index):
            model.setData(index, editor.currentText())

    class RegexDelegate(QStyledItemDelegate):
        """Delegate mit Regex-Validator (z. B. für Personalnummern)."""

        def __init__(self, pattern: str, parent=None):
            super().__init__(parent)
            self.rx = QRegularExpression(pattern)

        def createEditor(self, parent, option, index):
            ed = QLineEdit(parent)
            ed.setValidator(QRegularExpressionValidator(self.rx, ed))
            return ed

    # ===== TableModels =====
    class MitarbeiterTableModel(QAbstractTableModel):
        """Tabellenmodell für Mitarbeiter.csv (editierbar)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.headers = list(MITARBEITER_HEADERS)
            self.rows: List[List[str]] = []
            self.dirty: bool = False
            self.load()

        def load(self) -> None:
            self.beginResetModel()
            data = read_csv_rows(MITARBEITER_CSV)
            self.rows = [[r.get(h, "") for h in self.headers] for r in data]
            self.dirty = False
            self.endResetModel()

        def save(self) -> None:
            write_csv_rows(
                MITARBEITER_CSV,
                [dict(zip(self.headers, row)) for row in self.rows],
                self.headers,
            )
            self.dirty = False

        def rowCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.rows)

        def columnCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.headers)

        def data(self, index, role=Qt.DisplayRole):
            if not index.isValid():
                return None
            if role in (Qt.DisplayRole, Qt.EditRole):
                r, c = index.row(), index.column()
                return self.rows[r][c] if 0 <= r < len(self.rows) and 0 <= c < len(self.headers) else ""
            return None

        def setData(self, index, value, role=Qt.EditRole):
            if not index.isValid() or role != Qt.EditRole:
                return False
            r, c = index.row(), index.column()
            self.rows[r][c] = str(value)
            self.dirty = True
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True

        def flags(self, index):
            if not index.isValid():
                return Qt.ItemIsEnabled
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

        def headerData(self, section, orientation, role=Qt.DisplayRole):
            if role != Qt.DisplayRole:
                return None
            if orientation == Qt.Horizontal and 0 <= section < len(self.headers):
                return self.headers[section]
            if orientation == Qt.Vertical:
                return section + 1
            return None

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

    class AttendanceTableModel(QAbstractTableModel):
        """Tabellenmodell für Anwesenheit.csv (editierbar)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.headers = list(ANWESENHEIT_HEADERS)
            self.rows: List[List[str]] = []
            self.dirty: bool = False
            self.load()

        def load(self) -> None:
            self.beginResetModel()
            data = read_csv_rows(ANWESENHEIT_CSV)
            data.sort(key=lambda r: (r.get("Personalnummer", ""), r.get("Datum", "")))
            self.rows = [[r.get(h, "") for h in self.headers] for r in data]
            self.dirty = False
            self.endResetModel()

        def save(self) -> None:
            write_csv_rows(
                ANWESENHEIT_CSV,
                [dict(zip(self.headers, row)) for row in self.rows],
                self.headers,
            )
            self.dirty = False

        def rowCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.rows)

        def columnCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.headers)

        def data(self, index, role=Qt.DisplayRole):
            if not index.isValid():
                return None
            if role in (Qt.DisplayRole, Qt.EditRole):
                r, c = index.row(), index.column()
                return self.rows[r][c] if 0 <= r < len(self.rows) and 0 <= c < len(self.headers) else ""
            return None

        def setData(self, index, value, role=Qt.EditRole):
            if not index.isValid() or role != Qt.EditRole:
                return False
            r, c = index.row(), index.column()
            self.rows[r][c] = str(value)
            self.dirty = True
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True

        def flags(self, index):
            if not index.isValid():
                return Qt.ItemIsEnabled
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

        def headerData(self, section, orientation, role=Qt.DisplayRole):
            if role != Qt.DisplayRole:
                return None
            if orientation == Qt.Horizontal and 0 <= section < len(self.headers):
                return self.headers[section]
            if orientation == Qt.Vertical:
                return section + 1
            return None

    # ===== Dialoge =====
    class AddPersonDialog(QDialog):
        """Dialog zum Anlegen einer neuen Person (inkl. Anwesenheitsgenerierung)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Person hinzufügen")
            self.resize(500, 270)

            self.edPN = QLineEdit()
            self.edPN.setPlaceholderText("z.B. 00001234")
            self.edPN.setMaxLength(8)
            self.edPN.setValidator(
                QRegularExpressionValidator(QRegularExpression(r"^\d{0,8}$"), self)
            )

            self.edNa = QLineEdit()
            self.edNa.setPlaceholderText("Nachname")
            self.edVo = QLineEdit()
            self.edVo.setPlaceholderText("Vorname")

            self.cbMod = QComboBox()
            self.cbMod.addItems(
                ["Vollzeit (41 Std.)", "Vollzeit mit Kind (40 Std.)", "Teilzeit", "Eingliederung"]
            )

            self.cbDg = QComboBox()
            self.cbTe = QComboBox()
            self._reload_lists()

            form = QVBoxLayout(self)

            def row(lbl, w):
                h = QHBoxLayout()
                h.addWidget(QLabel(lbl))
                h.addWidget(w)
                form.addLayout(h)

            row("Personalnummer:", self.edPN)
            row("Nachname:", self.edNa)
            row("Vorname:", self.edVo)
            row("Arbeitszeitmodell:", self.cbMod)
            row("Dienstgrad:", self.cbDg)
            row("Teileinheit:", self.cbTe)

            btns = QHBoxLayout()
            self.btnCancel = QPushButton("Abbrechen")
            self.btnSave = QPushButton("Speichern")
            self.btnSave.setDefault(True)
            self.btnSave.setAutoDefault(True)
            self.btnCancel.setAutoDefault(False)
            btns.addStretch()
            btns.addWidget(self.btnCancel)
            btns.addWidget(self.btnSave)
            form.addLayout(btns)

            self.btnCancel.clicked.connect(self.reject)
            self.btnSave.clicked.connect(self.on_save)
            self.edPN.setFocus()

        def _reload_lists(self) -> None:
            dgs = read_single_column_values(DIENSTGRADE_CSV, "Dienstgrad")
            tes = read_single_column_values(TEILEINHEITEN_CSV, "Teileinheit")
            self.cbDg.clear()
            self.cbDg.addItems(dgs)
            self.cbTe.clear()
            self.cbTe.addItems(tes)

        def on_save(self) -> None:
            import re

            pn = self.edPN.text().strip()
            na = self.edNa.text().strip()
            vo = self.edVo.text().strip()
            md = self.cbMod.currentText().strip()
            dg = self.cbDg.currentText().strip()
            te = self.cbTe.currentText().strip()

            if not re.fullmatch(r"\d{8}", pn):
                QMessageBox.warning(
                    self,
                    "Eingabe prüfen",
                    "Die Personalnummer muss genau 8 Ziffern haben (z.B. 00001234).",
                )
                return
            if not na or not vo:
                QMessageBox.warning(
                    self, "Eingabe prüfen", "Bitte Nachname und Vorname angeben."
                )
                return
            if not dg or not te:
                QMessageBox.warning(
                    self,
                    "Eingabe prüfen",
                    "Bitte Dienstgrad und Teileinheit wählen/erfassen.",
                )
                return

            rows = read_csv_rows(MITARBEITER_CSV)
            if any(r.get("Personalnummer") == pn for r in rows):
                QMessageBox.warning(
                    self, "Duplikat", f"Die Personalnummer {pn} ist bereits vergeben."
                )
                return

            rows.append(
                {
                    "Personalnummer": pn,
                    "Nachname": na,
                    "Vorname": vo,
                    "Arbeitszeitmodell": md,
                    "Dienstgrad": dg,
                    "Teileinheit": te,
                }
            )
            try:
                write_csv_rows(MITARBEITER_CSV, rows, MITARBEITER_HEADERS)
                generate_attendance_for_person(pn)
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Fehler beim Speichern", str(e))

    class _SingleListModel(QAbstractTableModel):
        """Einspaltenmodell für Dienstgrade/Teileinheiten (editierbar)."""

        def __init__(self, values: List[str], parent=None):
            super().__init__(parent)
            self.values = list(values)

        def set_values(self, values: List[str]) -> None:
            self.beginResetModel()
            self.values = list(values)
            self.endResetModel()

        def rowCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.values)

        def columnCount(self, parent=QModelIndex()):
            return 1

        def data(self, index, role=Qt.DisplayRole):
            if not index.isValid():
                return None
            if role in (Qt.DisplayRole, Qt.EditRole):
                return self.values[index.row()]
            return None

        def setData(self, index, value, role=Qt.EditRole):
            if not index.isValid() or role != Qt.EditRole:
                return False
            self.values[index.row()] = str(value)
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True

        def headerData(self, section, orientation, role=Qt.DisplayRole):
            if role != Qt.DisplayRole:
                return None
            if orientation == Qt.Horizontal:
                return "Wert"
            return section + 1

        def flags(self, index):
            base = Qt.ItemIsEnabled
            if index.isValid():
                base |= Qt.ItemIsSelectable | Qt.ItemIsEditable
            return base

        def insertRows(self, row, count, parent=QModelIndex()):
            if row < 0:
                row = self.rowCount()
            self.beginInsertRows(parent, row, row + count - 1)
            for _ in range(count):
                self.values.insert(row, "")
            self.endInsertRows()
            return True

        def removeRows(self, row, count, parent=QModelIndex()):
            if row < 0 or row + count > len(self.values):
                return False
            self.beginRemoveRows(parent, row, row + count - 1)
            for _ in range(count):
                del self.values[row]
            self.endRemoveRows()
            return True

    class SingleListEditor(QDialog):
        """Dialog zum Bearbeiten von Dienstgraden/Teileinheiten (Einspaltenlisten)."""

        def __init__(self, title: str, path: Path, colname: str, parent=None):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.resize(520, 420)
            self.path = path
            self.colname = colname
            self.values: List[str] = read_single_column_values(self.path, self.colname)
            self.model = _SingleListModel(self.values)

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
            self.btnSave = QPushButton("Speichern")
            self.btnClose = QPushButton("Schließen")

            top = QHBoxLayout()
            top.addWidget(QLabel(f"Liste: {self.path.name}"))
            top.addStretch()

            btns = QHBoxLayout()
            btns.addWidget(self.btnAdd)
            btns.addWidget(self.btnDel)
            btns.addStretch()
            btns.addWidget(self.btnSave)
            btns.addWidget(self.btnClose)

            lay = QVBoxLayout(self)
            lay.addLayout(top)
            lay.addWidget(self.table)
            lay.addLayout(btns)

            self.btnAdd.clicked.connect(self.on_add)
            self.btnDel.clicked.connect(self.on_del)
            self.btnSave.clicked.connect(self.on_save)
            self.btnClose.clicked.connect(self.accept)

        def on_add(self) -> None:
            self.model.insertRows(self.model.rowCount(), 1)
            self.table.scrollToBottom()

        def on_del(self) -> None:
            sel = self.table.selectionModel().selectedRows()
            for ix in sorted(sel, key=lambda i: i.row(), reverse=True):
                self.model.removeRows(ix.row(), 1)

        def on_save(self) -> None:
            vals = [v.strip() for v in self.model.values if v.strip()]
            seen = set()
            clean: List[str] = []
            for v in vals:
                if v not in seen:
                    clean.append(v)
                    seen.add(v)
            try:
                write_single_column_values(self.path, self.colname, clean)
                QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{self.path}")
                self.model.set_values(clean)
            except Exception as e:
                QMessageBox.critical(self, "Fehler", str(e))

    class MitarbeiterEditor(QDialog):
        """Editor-Dialog für die Mitarbeitertabelle."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Mitarbeiter")
            self.resize(1000, 600)

            self.model = MitarbeiterTableModel(self)
            self.table = QTableView()
            self.table.setModel(self.model)
            self._reload_option_lists()
            self._apply_delegates()
            self.table.setSortingEnabled(True)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setAlternatingRowColors(True)
            self.table.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
                | QAbstractItemView.AnyKeyPressed
            )
            self.table.resizeColumnsToContents()

            self.btnReload = QPushButton("Neu laden")
            self.btnAddRow = QPushButton("Zeile +")
            self.btnDelRow = QPushButton("Zeile −")
            self.btnDelete = QPushButton("Löschen")
            self.btnDelete.setEnabled(False)
            self.btnAddPerson = QPushButton("Person hinzufügen")
            self.btnSave = QPushButton("Speichern")
            self.btnSave.setEnabled(False)
            self.btnClose = QPushButton("Schließen")

            top = QHBoxLayout()
            top.addWidget(QLabel("Tabelle: Mitarbeiter.csv"))
            top.addStretch()

            btns = QHBoxLayout()
            btns.addWidget(self.btnReload)
            btns.addWidget(self.btnAddRow)
            btns.addWidget(self.btnDelRow)
            btns.addWidget(self.btnDelete)
            btns.addWidget(self.btnAddPerson)
            btns.addStretch()
            btns.addWidget(self.btnSave)
            btns.addWidget(self.btnClose)

            lay = QVBoxLayout(self)
            lay.addLayout(top)
            lay.addWidget(self.table)
            lay.addLayout(btns)

            QShortcut(QKeySequence.Save, self, activated=lambda: self.on_save(silent=False))

            self.btnReload.clicked.connect(self.on_reload)
            self.btnAddRow.clicked.connect(self.on_add_row)
            self.btnDelRow.clicked.connect(self.on_del_row)
            self.btnDelete.clicked.connect(self.on_del_row)
            self.btnAddPerson.clicked.connect(self.on_add_person)
            self.btnSave.clicked.connect(lambda: self.on_save(silent=False))
            self.btnClose.clicked.connect(self.accept)

            self.model.dataChanged.connect(lambda *_: self._update_save_enabled())
            self.model.rowsInserted.connect(lambda *_: self._update_save_enabled())
            self.model.rowsRemoved.connect(lambda *_: self._update_save_enabled())
            self._update_save_enabled()

            self.table.selectionModel().selectionChanged.connect(self._update_delete_enabled)

        def _reload_option_lists(self) -> None:
            self._dienstgrade = read_single_column_values(DIENSTGRADE_CSV, "Dienstgrad")
            self._teileinheiten = read_single_column_values(TEILEINHEITEN_CSV, "Teileinheit")

        def _apply_delegates(self) -> None:
            def idx(name: str) -> int:
                try:
                    return self.model.headers.index(name)
                except ValueError:
                    return -1

            col_mod = idx("Arbeitszeitmodell")
            col_dg = idx("Dienstgrad")
            col_te = idx("Teileinheit")
            col_pn = idx("Personalnummer")

            if col_mod != -1:
                self.table.setItemDelegateForColumn(
                    col_mod,
                    ComboBoxDelegate(
                        ["Vollzeit (41 Std.)", "Vollzeit mit Kind (40 Std.)", "Teilzeit", "Eingliederung"], self.table
                    ),
                )
            if col_dg != -1:
                self.table.setItemDelegateForColumn(col_dg, ComboBoxDelegate(self._dienstgrade, self.table))
            if col_te != -1:
                self.table.setItemDelegateForColumn(col_te, ComboBoxDelegate(self._teileinheiten, self.table))
            if col_pn != -1:
                self.table.setItemDelegateForColumn(col_pn, RegexDelegate(r"^\d{8}$", self.table))

        def on_reload(self) -> None:
            self.model.load()
            self._reload_option_lists()
            self._apply_delegates()
            self.table.clearSelection()
            self.table.resizeColumnsToContents()
            self._update_delete_enabled()
            self._update_save_enabled()

        def on_add_row(self) -> None:
            self.model.insertRows(self.model.rowCount(), 1)
            self.table.scrollToBottom()
            self._update_delete_enabled()
            self._update_save_enabled()

        def _selected_rows_info(self):
            headers = self.model.headers
            i_pn = headers.index("Personalnummer") if "Personalnummer" in headers else -1
            i_na = headers.index("Nachname") if "Nachname" in headers else -1
            i_vo = headers.index("Vorname") if "Vorname" in headers else -1
            sel = self.table.selectionModel().selectedRows()
            lines = []
            pns = []
            for ix in sel:
                r = ix.row()
                row = self.model.rows[r]
                pn = row[i_pn] if i_pn != -1 else ""
                na = row[i_na] if i_na != -1 else ""
                vo = row[i_vo] if i_vo != -1 else ""
                lines.append(f"- {na}, {vo} (PN {pn})")
                pns.append(pn)
            return lines, pns, sel

        def on_del_row(self) -> None:
            lines, pns, sel = self._selected_rows_info()
            if not sel:
                return

            text = "Soll(en) die folgende(n) Person(en) endgültig gelöscht werden?\n\n" + "\n".join(lines)
            ret = QMessageBox.question(
                self,
                "Löschen bestätigen",
                text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return

            for ix in sorted(sel, key=lambda i: i.row(), reverse=True):
                self.model.removeRows(ix.row(), 1)

            for pn in pns:
                if pn:
                    remove_attendance_for_person(pn)

            try:
                self.model.save()
                QMessageBox.information(self, "Gelöscht", "Ausgewählte Person(en) wurden gelöscht.")
            except Exception as e:
                QMessageBox.critical(self, "Fehler beim Speichern", str(e))

            self.table.clearSelection()
            self._update_delete_enabled()
            self._update_save_enabled()
            self.table.resizeColumnsToContents()

        def on_add_person(self) -> None:
            dlg = AddPersonDialog(self)
            if dlg.exec():
                self.on_reload()

        def _update_delete_enabled(self, *args) -> None:
            has_sel = bool(self.table.selectionModel().selectedRows())
            self.btnDelete.setEnabled(has_sel)
            self.btnDelRow.setEnabled(has_sel)

        def _update_save_enabled(self) -> None:
            self.btnSave.setEnabled(getattr(self.model, "dirty", False))

        def _validate(self) -> str:
            headers = self.model.headers

            def idx(name: str) -> int:
                try:
                    return headers.index(name)
                except ValueError:
                    return -1

            i_pn = idx("Personalnummer")
            pns = [row[i_pn].strip() for row in self.model.rows if i_pn != -1]
            bad_len = [p for p in pns if not p or len(p) != 8 or not p.isdigit()]
            dupes = []
            seen = set()
            for p in pns:
                if p in seen and p not in dupes:
                    dupes.append(p)
                seen.add(p)

            msgs = []
            if bad_len:
                msgs.append("Ungültige PNs (müssen 8 Ziffern sein): " + ", ".join(sorted(set(bad_len))))
            if dupes:
                msgs.append("Doppelte PNs: " + ", ".join(sorted(dupes)))
            return "\n".join(msgs)

        def on_save(self, silent: bool = False) -> bool:
            msg = self._validate()
            if msg:
                if not silent:
                    QMessageBox.warning(self, "Eingaben prüfen", msg + "\n\nSpeichern abgebrochen.")
                return False
            try:
                if self.model.dirty:
                    self.model.save()
                    if not silent:
                        QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{MITARBEITER_CSV}")
                self._update_save_enabled()
                return True
            except Exception as e:
                if not silent:
                    QMessageBox.critical(self, "Fehler", str(e))
                return False

    class AttendanceEditor(QDialog):
        """Editor-Dialog für die Anwesenheitstabelle."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Anwesenheit")
            self.resize(1100, 650)

            self.model = AttendanceTableModel(self)
            self.table = QTableView()
            self.table.setModel(self.model)
            self.table.setSortingEnabled(True)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setAlternatingRowColors(True)
            self.table.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
                | QAbstractItemView.AnyKeyPressed
            )
            self.table.resizeColumnsToContents()

            self.edFilterPN = QLineEdit()
            self.edFilterPN.setPlaceholderText("PN filtern (8-stellig)")
            self.btnReload = QPushButton("Neu laden")
            self.btnSave = QPushButton("Speichern")
            self.btnClose = QPushButton("Schließen")

            top = QHBoxLayout()
            top.addWidget(QLabel("Anwesenheit.csv"))
            top.addStretch()
            top.addWidget(QLabel("Filter PN:"))
            top.addWidget(self.edFilterPN)
            top.addWidget(self.btnReload)
            top.addWidget(self.btnSave)
            top.addWidget(self.btnClose)

            lay = QVBoxLayout(self)
            lay.addLayout(top)
            lay.addWidget(self.table)

            self.btnReload.clicked.connect(self.on_reload)
            self.btnSave.clicked.connect(self.on_save)
            self.btnClose.clicked.connect(self.accept)
            self.edFilterPN.textChanged.connect(self.apply_filter)

        def on_reload(self) -> None:
            self.model.load()
            self.apply_filter()
            self.table.resizeColumnsToContents()

        def on_save(self) -> None:
            try:
                if self.model.dirty:
                    self.model.save()
                QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{ANWESENHEIT_CSV}")
            except Exception as e:
                QMessageBox.critical(self, "Fehler", str(e))

        def apply_filter(self) -> None:
            pn = self.edFilterPN.text().strip()
            if not pn:
                return
            data = read_csv_rows(ANWESENHEIT_CSV)
            if pn:
                data = [r for r in data if pn in (r.get("Personalnummer", ""))]
            self.model.beginResetModel()
            self.model.rows = [[r.get(h, "") for h in self.model.headers] for r in data]
            self.model.endResetModel()

    # ===== UI laden / Buttons verdrahten =====
    def load_ui_mainwindow():
        loader = QUiLoader()
        f = QFile(str(ui_file))
        if not f.open(QFile.ReadOnly):
            raise RuntimeError(f"Konnte UI nicht öffnen: {ui_file}")
        win: QWidget = loader.load(f)
        f.close()

        needed = {
            "btnEdit_2": _QPushButton,  # Personal
            "btnEdit_3": _QPushButton,  # Anwesenheit
            "btnEdit_5": _QPushButton,  # Dienstgrade
            "btnEdit_6": _QPushButton,  # Teileinheiten
        }
        for obj, cls in needed.items():
            w = win.findChild(cls, obj)
            if w is None:
                raise RuntimeError(f"Button '{obj}' wurde in der UI nicht gefunden.")
            setattr(win, obj, w)
        return win

    def wire_main_buttons(win) -> None:
        def open_personal():
            MitarbeiterEditor(win).exec()

        def open_anwesenheit():
            AttendanceEditor(win).exec()

        def open_dienstgrade():
            SingleListEditor("Dienstgrade bearbeiten", DIENSTGRADE_CSV, "Dienstgrad", win).exec()

        def open_teileinheiten():
            SingleListEditor("Teileinheiten bearbeiten", TEILEINHEITEN_CSV, "Teileinheit", win).exec()

        win.btnEdit_2.clicked.connect(open_personal)
        win.btnEdit_3.clicked.connect(open_anwesenheit)
        win.btnEdit_5.clicked.connect(open_dienstgrade)
        win.btnEdit_6.clicked.connect(open_teileinheiten)

    # ===== Starten =====
    ensure_all_csvs()
    app = QApplication(sys.argv)
    try:
        win = load_ui_mainwindow()
    except Exception as e:
        QMessageBox.critical(None, "Fehler", str(e))
        return 1
    wire_main_buttons(win)
    win.show()
    return app.exec()


def main() -> int:
    """
    Startet im Normalfall die GUI.
    In Headless/CI-Umgebungen (PP_HEADLESS=1) werden nur CSVs angelegt,
    damit Import/Tests ohne PySide6 funktionieren.
    """
    ensure_all_csvs()
    if os.environ.get("PP_HEADLESS", "0") == "1":
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
