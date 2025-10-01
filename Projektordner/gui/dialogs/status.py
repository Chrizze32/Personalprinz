# gui/status.py
from __future__ import annotations
from typing import List, Dict, Callable

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView,
    QPushButton, QLabel, QAbstractItemView, QMessageBox,
    QLineEdit, QFormLayout, QDialogButtonBox, QStyledItemDelegate,
    QWidget, QComboBox, QDoubleSpinBox
)

from .mitarbeiter import DictTableModel  # generisches Tabellenmodell
from storage import STATUS_CSV, STATUS_HEADERS

# ===== Regeln (ohne 'fix_soll') + einfache Erklärungen =====
RULE_CHOICES = [
    "anwesend",          # reine Netto-Anwesenheit (mit Pausen)
    "null",              # keine Zeitbewegung
    "zeitausgleich",     # Tages-Soll wird vom Zeitkonto abgezogen
    "mehrarbeit",        # nur Zeit über Tages-Soll zählt als Mehrarbeit
    "abbau_mehrarbeit",  # Mehrarbeitskonto wird um Tages-Soll verringert
    "fvd_tag",           # 1 FvD-Tag wird gezählt
]
RULE_TEXT: Dict[str, str] = {
    "anwesend": "Zählt nur die tatsächliche Anwesenheit (mit Pausen).",
    "null": "Keine Zeit wird abgezogen oder gutgeschrieben (z. B. Urlaub, Krank, Wochenende, Feiertag).",
    "zeitausgleich": "Zieht die Tages-Sollzeit vom Zeitkonto ab.",
    "mehrarbeit": "Nur die Zeit über der Tages-Sollzeit zählt als Mehrarbeit.",
    "abbau_mehrarbeit": "Verringert das Mehrarbeitskonto um die Tages-Sollzeit.",
    "fvd_tag": "Zählt einen FvD-Tag.",
}

# ===== Standard-Status: Name -> (Sollstunden, Regel) =====
READONLY_DEFAULTS: Dict[str, tuple[str, str]] = {
    "Anwesend": ("", "anwesend"),
    "Urlaub": ("", "null"),
    "Home Office": ("", "null"),
    "Dienstreise": ("", "null"),
    "Zeitausgleich": ("", "zeitausgleich"),
    "Mehrarbeit": ("", "mehrarbeit"),
    "Abbau Mehrarbeit": ("", "abbau_mehrarbeit"),
    "FvD": ("", "fvd_tag"),
    "Krank": ("", "null"),
    "Kindkrank": ("", "null"),
    "Nicht mehr in Kompanie": ("", "null"),
    "Wochenende": ("", "null"),
    "Feiertag": ("", "null"),
}

# ===== Delegates =====

class RuleDelegate(QStyledItemDelegate):
    """ComboBox-Editor für Spalte 'Regel' mit Tooltips zu jeder Regel."""
    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        for rule in RULE_CHOICES:
            cb.addItem(rule)
            cb.setItemData(cb.count()-1, RULE_TEXT.get(rule, ""), Qt.ToolTipRole)
        cb.setStyleSheet("QComboBox { background-color: white; } QAbstractItemView { background-color: white; }")
        return cb

    def setEditorData(self, editor: QComboBox, index):
        val = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        i = editor.findText(val)
        if i >= 0:
            editor.setCurrentIndex(i)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)


class HoursDelegate(QStyledItemDelegate):
    """SpinBox-Editor für 'Sollstunden' (0..80h, Schritt 0.25)."""
    def createEditor(self, parent, option, index):
        sb = QDoubleSpinBox(parent)
        sb.setDecimals(2)
        sb.setRange(0.0, 80.0)
        sb.setSingleStep(0.25)
        sb.setStyleSheet("QDoubleSpinBox { background-color: white; }")
        return sb

    def setEditorData(self, editor: QDoubleSpinBox, index):
        txt = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "").replace(",", ".")
        try:
            editor.setValue(float(txt) if txt else 0.0)
        except Exception:
            editor.setValue(0.0)

    def setModelData(self, editor: QDoubleSpinBox, model, index):
        val = f"{editor.value():.2f}".rstrip("0").rstrip(".")
        model.setData(index, val, Qt.EditRole)


class ReadOnlyAwareDelegate(QStyledItemDelegate):
    """Verhindert Editor-Erstellung für gesperrte Zellen (Standard-Status: Name & Regel)."""
    def __init__(self, is_readonly_cell: Callable[[QModelIndex], bool], parent=None):
        super().__init__(parent)
        self._is_ro = is_readonly_cell

    def createEditor(self, parent, option, index):
        if self._is_ro(index):
            return None
        return super().createEditor(parent, option, index)


# ===== Add-Dialog =====

class StatusAddDialog(QDialog):
    """Popup zum Hinzufügen: Status + Sollstunden + Regel, mit Live-Erklärung."""
    def __init__(self, existing_names: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Status hinzufügen")
        self._existing = {s.strip().lower() for s in existing_names}
        self.values: Dict[str, str] = {"Status": "", "Sollstunden": "", "Regel": "anwesend"}

        self.edName = QLineEdit()
        self.sbHours = QDoubleSpinBox()
        self.sbHours.setDecimals(2); self.sbHours.setRange(0.0, 80.0); self.sbHours.setSingleStep(0.25)

        self.cbRule = QComboBox()
        for rule in RULE_CHOICES:
            self.cbRule.addItem(rule)
            self.cbRule.setItemData(self.cbRule.count()-1, RULE_TEXT.get(rule, ""), Qt.ToolTipRole)

        self.lblRuleInfo = QLabel(RULE_TEXT["anwesend"])
        self.lblRuleInfo.setWordWrap(True)  # gut lesbar, nicht ausgegraut

        form = QFormLayout()
        form.addRow("Status:", self.edName)
        form.addRow("Sollstunden:", self.sbHours)
        form.addRow("Regel:", self.cbRule)
        form.addRow("", self.lblRuleInfo)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)
        self.edName.setFocus()

        self.cbRule.currentTextChanged.connect(
            lambda r: self.lblRuleInfo.setText(RULE_TEXT.get(r, ""))
        )

    def _on_ok(self):
        name = self.edName.text().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Bitte einen Status-Namen eingeben.")
            return
        if name.lower() in self._existing:
            QMessageBox.warning(self, "Fehler", f"„{name}“ existiert bereits.")
            return
        hours = f"{self.sbHours.value():.2f}".rstrip("0").rstrip(".")
        rule = self.cbRule.currentText()
        self.values = {"Status": name, "Sollstunden": hours, "Regel": rule}
        self.accept()


# ===== Hauptdialog =====

class StatusDialog(QDialog):
    """
    Editor für Status.csv (Status, Sollstunden, Regel)
    - Standard-Status: Name & Regel schreibgeschützt, nicht löschbar
    - Buttons: Status hinzufügen, Status löschen, Speichern, Schließen
    - Unter der Tabelle: einfache Erklärung zur gewählten Regel
    """
    COL_STATUS = 0
    COL_HOURS = 1
    COL_RULE = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Status-Liste")
        self.model = DictTableModel(STATUS_HEADERS, STATUS_CSV, self)

        # Upgrade älterer Dateien:
        #   - Wenn eine „Beschreibung“-Spalte existiert, wird sie ignoriert (wir zeigen die Erklärung unten an).
        #   - Ziel: Spalten genau ["Status","Sollstunden","Regel"]
        target_headers = ["Status", "Sollstunden", "Regel"]
        if self.model.headers != target_headers:
            # Mapping vorhandener Spalten in Ziel
            old_idx = {h: i for i, h in enumerate(self.model.headers)}
            new_rows: List[List[str]] = []
            for row in self.model.rows:
                vals = ["", "", ""]
                for i, h in enumerate(target_headers):
                    if h in old_idx and old_idx[h] < len(row):
                        vals[i] = row[old_idx[h]]
                new_rows.append(vals)
            self.model.headers = target_headers
            self.model.rows = new_rows

        # Defaults für Standard-Status (falls leer)
        for r in range(self.model.rowCount()):
            name = (self.model.rows[r][self.COL_STATUS] or "").strip()
            if name in READONLY_DEFAULTS:
                def_soll, def_rule = READONLY_DEFAULTS[name]
                if not (self.model.rows[r][self.COL_RULE] or "").strip():
                    self.model.rows[r][self.COL_RULE] = def_rule
                if not (self.model.rows[r][self.COL_HOURS] or "").strip():
                    self.model.rows[r][self.COL_HOURS] = def_soll

        # Tabelle
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.resizeColumnsToContents()

        # Delegates
        self.table.setItemDelegateForColumn(self.COL_HOURS, HoursDelegate(self.table))
        self.table.setItemDelegateForColumn(self.COL_RULE, RuleDelegate(self.table))

        def is_readonly_cell(ix: QModelIndex) -> bool:
            if not ix.isValid():
                return False
            row = ix.row(); col = ix.column()
            name = (self.model.rows[row][self.COL_STATUS] or "").strip()
            if name in READONLY_DEFAULTS and col in (self.COL_STATUS, self.COL_RULE):
                return True
            return False

        self.table.setItemDelegate(ReadOnlyAwareDelegate(is_readonly_cell, self.table))

        # Buttons mit gewünschten Bezeichnungen
        self.btnAdd = QPushButton("Status hinzufügen")
        self.btnDel = QPushButton("Status löschen")
        self.btnSave = QPushButton("Speichern")
        self.btnClose = QPushButton("Schließen")

        top = QHBoxLayout()
        top.addWidget(QLabel("Liste: Status.csv"))
        top.addStretch()

        btns = QHBoxLayout()
        btns.addWidget(self.btnAdd)
        btns.addWidget(self.btnDel)
        btns.addStretch()
        btns.addWidget(self.btnSave)
        btns.addWidget(self.btnClose)

        # Erklärung-Panel (nicht ausgegraut, einfache Sprache)
        self.lblInfo = QLabel("")
        self.lblInfo.setWordWrap(True)  # klar lesbar

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(btns)
        lay.addWidget(self.lblInfo)

        # Aktionen
        self.btnAdd.clicked.connect(self._on_add)
        self.btnDel.clicked.connect(self._on_del)
        self.btnSave.clicked.connect(self._on_save)
        self.btnClose.clicked.connect(self.accept)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # initiale Info
        self._on_selection_changed()

    # ----- Helpers -----

    def _is_readonly_row(self, row: int) -> bool:
        name = (self.model.rows[row][self.COL_STATUS] or "").strip()
        return name in READONLY_DEFAULTS

    def _update_info_label_for_row(self, row: int):
        if row < 0 or row >= self.model.rowCount():
            self.lblInfo.setText("")
            return
        rule = (self.model.rows[row][self.COL_RULE] or "").strip()
        txt = RULE_TEXT.get(rule, "")
        if rule:
            self.lblInfo.setText(f"Regel „{rule}“: {txt}")
        else:
            self.lblInfo.setText("")

    # ----- Slots -----

    def _on_selection_changed(self, *args):
        sel = self.table.selectionModel().selectedRows()
        self._update_info_label_for_row(sel[0].row() if sel else -1)

    def _on_add(self):
        existing = [(r[self.COL_STATUS] or "").strip() for r in self.model.rows]
        dlg = StatusAddDialog(existing, self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values
        self.model.insertRows(self.model.rowCount(), 1)
        r = self.model.rowCount() - 1
        self.model.setData(self.model.index(r, self.COL_STATUS), vals["Status"], Qt.EditRole)
        self.model.setData(self.model.index(r, self.COL_HOURS), vals["Sollstunden"], Qt.EditRole)
        self.model.setData(self.model.index(r, self.COL_RULE), vals["Regel"], Qt.EditRole)
        self.table.selectRow(r)
        self.table.scrollToBottom()
        self._update_info_label_for_row(r)

    def _on_del(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        if self._is_readonly_row(r):
            QMessageBox.information(self, "Hinweis", "Dieser Standard-Status kann nicht gelöscht werden.")
            return
        name = (self.model.rows[r][self.COL_STATUS] or "").strip() or "unbenannt"
        ans = QMessageBox.question(
            self,
            "Status löschen",
            f"Sind Sie sich sicher, dass Sie den Eintrag „{name}“ löschen wollen?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans != QMessageBox.Yes:
            return
        self.model.removeRows(r, 1)

    def _on_save(self):
        # Standardzeilen fixieren (Name & Regel)
        for r in range(self.model.rowCount()):
            name = (self.model.rows[r][self.COL_STATUS] or "").strip()
            if name in READONLY_DEFAULTS:
                def_soll, def_rule = READONLY_DEFAULTS[name]
                self.model.rows[r][self.COL_RULE] = def_rule
                if not (self.model.rows[r][self.COL_HOURS] or "").strip():
                    self.model.rows[r][self.COL_HOURS] = def_soll
        try:
            self.model.save()
            QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{STATUS_CSV}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))
