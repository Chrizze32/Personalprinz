# gui/arbeitszeitmodelle.py
from __future__ import annotations
from typing import List, Dict, Optional

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView,
    QPushButton, QLabel, QAbstractItemView, QMessageBox,
    QLineEdit, QFormLayout, QDialogButtonBox, QStyledItemDelegate,
    QWidget, QDoubleSpinBox
)

from .mitarbeiter import DictTableModel  # generisches Tabellenmodell
from storage import (
    ARBEITSZEITMODELLE_CSV,
    ARBEITSZEITMODELLE_HEADERS,
)

# ---- Spalten-Konstanten (Schema) ----
COLS = ["Modell", "Wochenstunden", "Mo", "Di", "Mi", "Do", "Fr"]
NAME_COL = 0
WEEK_COL = 1
DAY_COLS = [2, 3, 4, 5, 6]  # Mo..Fr
EPS = 0.01  # Rundungstoleranz in Stunden


# ---------- Delegates ----------

class HoursDelegate(QStyledItemDelegate):
    """SpinBox-Editor (wird nur im Form-Dialog genutzt, nicht in der Tabelle)."""
    def createEditor(self, parent, option, index):
        sb = QDoubleSpinBox(parent)
        sb.setDecimals(2)
        sb.setRange(0.0, 24.0)
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


# ---------- Reusable Form-Dialog für Add/Edit ----------

class AZFormDialog(QDialog):
    """
    Formular für Arbeitszeitmodell (Name, Woche, Mo–Fr) mit strenger Validierung.
    - Für 'Hinzufügen' und 'Bearbeiten' verwendbar.
    - Bei Edit: 'existing_except' ist der bisherige Name (damit er als unique gilt).
    """
    def __init__(self, existing_names: List[str], *, initial: Optional[Dict[str, str]] = None,
                 existing_except: Optional[str] = None, parent=None, title: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title or ("Arbeitszeitmodell" if initial else "Arbeitszeitmodell hinzufügen"))
        self._existing = {s.strip().lower() for s in existing_names}
        if existing_except:
            self._existing.discard(existing_except.strip().lower())
        self.values: Dict[str, str] = {k: "" for k in COLS}

        # Widgets
        self.edName = QLineEdit()
        self.sbWeek = QDoubleSpinBox(); self._fmt_week(self.sbWeek)

        self.sbMo = QDoubleSpinBox(); self._fmt_day(self.sbMo)
        self.sbDi = QDoubleSpinBox(); self._fmt_day(self.sbDi)
        self.sbMi = QDoubleSpinBox(); self._fmt_day(self.sbMi)
        self.sbDo = QDoubleSpinBox(); self._fmt_day(self.sbDo)
        self.sbFr = QDoubleSpinBox(); self._fmt_day(self.sbFr)

        # Prefill bei Edit
        if initial:
            self.edName.setText(initial.get("Modell", ""))
            self.sbWeek.setValue(self._to_f(initial.get("Wochenstunden")))
            self.sbMo.setValue(self._to_f(initial.get("Mo")))
            self.sbDi.setValue(self._to_f(initial.get("Di")))
            self.sbMi.setValue(self._to_f(initial.get("Mi")))
            self.sbDo.setValue(self._to_f(initial.get("Do")))
            self.sbFr.setValue(self._to_f(initial.get("Fr")))

        # Layout
        form = QFormLayout()
        form.addRow("Name:", self.edName)
        form.addRow("Wochenstunden:", self.sbWeek)
        form.addRow("Montag (h):", self.sbMo)
        form.addRow("Dienstag (h):", self.sbDi)
        form.addRow("Mittwoch (h):", self.sbMi)
        form.addRow("Donnerstag (h):", self.sbDo)
        form.addRow("Freitag (h):", self.sbFr)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)
        self.edName.setFocus()

    def _fmt_week(self, sb: QDoubleSpinBox):
        sb.setDecimals(2); sb.setRange(0.0, 80.0); sb.setSingleStep(0.25)

    def _fmt_day(self, sb: QDoubleSpinBox):
        sb.setDecimals(2); sb.setRange(0.0, 24.0); sb.setSingleStep(0.25)

    def _to_f(self, s: Optional[str]) -> float:
        try:
            return float((s or "0").replace(",", "."))
        except Exception:
            return 0.0

    def _on_ok(self):
        name = self.edName.text().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Bitte einen Modellnamen eingeben.")
            return
        if name.lower() in self._existing:
            QMessageBox.warning(self, "Fehler", f"„{name}“ existiert bereits.")
            return

        w = float(self.sbWeek.value())
        d = [float(self.sbMo.value()), float(self.sbDi.value()),
             float(self.sbMi.value()), float(self.sbDo.value()), float(self.sbFr.value())]
        sum_days = sum(d)

        # Strenge Regel: Wochenstunden müssen der Summe Mo–Fr entsprechen
        if abs(w - sum_days) > EPS:
            QMessageBox.critical(
                self, "Ungültige Eingabe",
                f"Die Wochenstunden ({w:.2f}) müssen exakt der Summe der Tagesstunden "
                f"({sum_days:.2f}) entsprechen."
            )
            return

        self.values = {
            "Modell": name,
            "Wochenstunden": f"{w:.2f}".rstrip('0').rstrip('.'),
            "Mo": f"{d[0]:.2f}".rstrip('0').rstrip('.'),
            "Di": f"{d[1]:.2f}".rstrip('0').rstrip('.'),
            "Mi": f"{d[2]:.2f}".rstrip('0').rstrip('.'),
            "Do": f"{d[3]:.2f}".rstrip('0').rstrip('.'),
            "Fr": f"{d[4]:.2f}".rstrip('0').rstrip('.'),
        }
        self.accept()


# ---------- Hauptdialog ----------

class ArbeitszeitmodelleDialog(QDialog):
    """
    Editor für arbeitszeitmodelle.csv: Modell, Wochenstunden, Mo–Fr.
    - Tabelle immer read-only (keine Direktbearbeitung).
    - Hinzufügen: öffnet Formular.
    - Bearbeiten: Zeile wählen → Button „Bearbeiten“ → Formular mit Vorbelegung.
    - Löschen: Sicherheitsabfrage mit Modellnamen.
    - Speichern: schreibt CSV; strenge Validierung aller Zeilen.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arbeitszeitmodelle")

        # Model laden (und ggf. upgraden)
        self.model = DictTableModel(ARBEITSZEITMODELLE_HEADERS, ARBEITSZEITMODELLE_CSV, self)
        self._upgrade_columns_if_needed()

        # Tabelle (immer read-only)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.resizeColumnsToContents()

        # Buttons
        self.btnAdd = QPushButton("Eintrag hinzufügen")
        self.btnEdit = QPushButton("Bearbeiten")
        self.btnDel = QPushButton("Eintrag löschen")
        self.btnSave = QPushButton("Speichern")
        self.btnClose = QPushButton("Schließen")

        top = QHBoxLayout()
        top.addWidget(QLabel("Liste: arbeitszeitmodelle.csv"))
        top.addStretch()

        btns = QHBoxLayout()
        btns.addWidget(self.btnAdd)
        btns.addWidget(self.btnEdit)
        btns.addWidget(self.btnDel)
        btns.addStretch()
        btns.addWidget(self.btnSave)
        btns.addWidget(self.btnClose)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(btns)

        # Actions
        self.btnAdd.clicked.connect(self._on_add)
        self.btnEdit.clicked.connect(self._on_edit)
        self.btnDel.clicked.connect(self._on_del)
        self.btnSave.clicked.connect(self._on_save)
        self.btnClose.clicked.connect(self.accept)

    # ---- Helpers ----

    def _upgrade_columns_if_needed(self):
        """
        Hebt alte Dateien auf das neue Schema an:
        - Reihenfolge/Headers = COLS
        - Fehlende Spalten werden mit "" ergänzt.
        """
        if self.model.headers != COLS:
            new_rows: List[List[str]] = []
            old_index = {h: i for i, h in enumerate(self.model.headers)}
            for row in self.model.rows:
                vals = [""] * len(COLS)
                for i, h in enumerate(COLS):
                    if h in old_index:
                        vals[i] = row[old_index[h]]
                new_rows.append(vals)
            self.model.headers = COLS[:]
            self.model.rows = new_rows

        for i in range(self.model.rowCount()):
            while len(self.model.rows[i]) < len(COLS):
                self.model.rows[i].append("")

    def _collect_existing_names(self, exclude_row: Optional[int] = None) -> List[str]:
        names = []
        for i, r in enumerate(self.model.rows):
            if exclude_row is not None and i == exclude_row:
                continue
            names.append((r[NAME_COL] or "").strip())
        return [n for n in names if n]

    def _row_values(self, row: int) -> Dict[str, str]:
        return {h: (self.model.rows[row][i] if i < len(self.model.rows[row]) else "")
                for i, h in enumerate(COLS)}

    def _to_f(self, s: str) -> float:
        try:
            return float((s or "0").replace(",", "."))
        except Exception:
            return 0.0

    # ---- Slots ----

    def _on_add(self):
        dlg = AZFormDialog(self._collect_existing_names(), parent=self, title="Arbeitszeitmodell hinzufügen")
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values
        self.model.insertRows(self.model.rowCount(), 1)
        r = self.model.rowCount() - 1
        for c, h in enumerate(COLS):
            self.model.setData(self.model.index(r, c), vals.get(h, ""), Qt.EditRole)
        self.table.selectRow(r)
        self.table.scrollToBottom()

    def _on_edit(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Hinweis", "Bitte wählen Sie zuerst einen Eintrag aus.")
            return
        r = sel[0].row()
        current = self._row_values(r)
        dlg = AZFormDialog(
            self._collect_existing_names(exclude_row=r),
            initial=current,
            existing_except=current.get("Modell", ""),
            parent=self,
            title=f"Arbeitszeitmodell bearbeiten – {current.get('Modell','')}"
        )
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values
        # Übernehmen in die selektierte Zeile
        for c, h in enumerate(COLS):
            self.model.setData(self.model.index(r, c), vals.get(h, ""), Qt.EditRole)

    def _on_del(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Hinweis", "Bitte wählen Sie zuerst einen Eintrag aus.")
            return
        r = sel[0].row()
        name = (self.model.rows[r][NAME_COL] or "").strip()
        if not name:
            name = "unbenannt"
        ans = QMessageBox.question(
            self,
            "Eintrag löschen",
            f"Sind Sie sich sicher, dass Sie den Eintrag „{name}“ löschen wollen?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans != QMessageBox.Yes:
            return
        self.model.removeRows(r, 1)

    def _on_save(self):
        # STRIKTE VALIDIERUNG für jede Zeile (nochmals vor Persistenz)
        for r in range(self.model.rowCount()):
            name = (self.model.rows[r][NAME_COL] or "").strip()
            if not name:
                QMessageBox.warning(self, "Fehler", f"Zeile {r+1}: Name/Modell darf nicht leer sein.")
                return

            w = self._to_f(self.model.rows[r][WEEK_COL])
            days = [self._to_f(self.model.rows[r][c]) for c in DAY_COLS]
            sum_days = sum(days)

            if abs(w - sum_days) > EPS:
                QMessageBox.critical(
                    self, "Ungültige Werte",
                    f"„{name}“: Wochenstunden ({w:.2f}) müssen der Summe Mo–Fr "
                    f"({sum_days:.2f}) entsprechen."
                )
                return

        try:
            self.model.save()
            QMessageBox.information(self, "Gespeichert", f"Datei gespeichert:\n{ARBEITSZEITMODELLE_CSV}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))
