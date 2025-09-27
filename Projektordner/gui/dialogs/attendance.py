# gui/dialogs/attendance.py
from __future__ import annotations
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Tuple

from PySide6.QtCore import (
    Qt, QModelIndex, QAbstractTableModel, QSortFilterProxyModel, QDate
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView, QWidget,
    QPushButton, QLabel, QAbstractItemView, QMessageBox, QGroupBox,
    QScrollArea, QLineEdit, QComboBox, QDateEdit
)

# Projekt-Storage/Logik
from storage import (
    MITARBEITER_CSV, MITARBEITER_HEADERS,
    TEILEINHEITEN_CSV,
    ANWESENHEIT_CSV, ANWESENHEIT_HEADERS,
    read_csv_rows, write_csv_rows,
)
from logic import generate_attendance_for_person


# ---------- Helpers: Anwesenheit für HEUTE setzen (ohne Überschreiben) ----------

def _ensure_today_row(pn: str) -> None:
    """Sicherstellen, dass es für heute eine Anwesenheitszeile zu dieser PN gibt (idempotent)."""
    generate_attendance_for_person(pn, path=ANWESENHEIT_CSV)


def _set_time_for_today(
    pn: str,
    anfang: Optional[str] = None,
    ende: Optional[str] = None,
    *,
    overwrite: bool = False,
) -> Tuple[int, int]:
    """
    Setzt Anfang/Ende für HEUTE.
    - Legt die heutige Zeile an, falls sie fehlt.
    - Überschreibt standardmäßig NICHT bestehende Werte (overwrite=False).
    Rückgabe: (changed_fields, skipped_fields)
    """
    rows = read_csv_rows(ANWESENHEIT_CSV)
    today = date.today().isoformat()

    target_row = None
    for r in rows:
        if r.get("Personalnummer") == pn and r.get("Datum") == today:
            target_row = r
            break

    if target_row is None:
        target_row = {h: "" for h in ANWESENHEIT_HEADERS}
        target_row["Personalnummer"] = pn
        target_row["Datum"] = today
        rows.append(target_row)

    changed_fields = 0
    skipped_fields = 0

    if anfang is not None:
        if overwrite or not (target_row.get("Anfang") or "").strip():
            target_row["Anfang"] = anfang
            changed_fields += 1
        else:
            skipped_fields += 1

    if ende is not None:
        if overwrite or not (target_row.get("Ende") or "").strip():
            target_row["Ende"] = ende
            changed_fields += 1
        else:
            skipped_fields += 1

    write_csv_rows(ANWESENHEIT_CSV, rows, ANWESENHEIT_HEADERS)
    return changed_fields, skipped_fields


# ---------- Datenanreicherung: Teileinheit je PN ----------

def _load_pn_to_te_map() -> Dict[str, str]:
    """Liest Mitarbeiter.csv und baut ein Mapping PN -> Teileinheit (leer, wenn Spalte fehlt)."""
    rows = read_csv_rows(MITARBEITER_CSV)
    # Spaltennamen robust ermitteln
    te_col = None
    for candidate in ("Teileinheit", "Teileinheiten", "TeilEinheit", "TE"):
        if candidate in MITARBEITER_HEADERS:
            te_col = candidate
            break

    m: Dict[str, str] = {}
    for r in rows:
        pn = (r.get("Personalnummer") or "").strip()
        if not pn:
            continue
        te = (r.get(te_col) or "").strip() if te_col else ""
        m[pn] = te
    return m


def _collect_te_list() -> List[str]:
    """Liste der Teileinheiten (Dropdown)."""
    rows = read_csv_rows(TEILEINHEITEN_CSV)
    vals = []
    for r in rows:
        # Single-List-Datei hat idR. genau eine Spalte; nimm die erste
        if r:
            vals.append(next(iter(r.values())))
    # uniq und sortiert, leere raus
    return sorted({v.strip() for v in vals if v and v.strip()})


# ---------- Model: gesamte Anwesenheit (mit 'Teileinheit'-Spalte angereichert) ----------

class AttendanceModel(QAbstractTableModel):
    """
    Zeigt alle Zeilen aus Anwesenheit.csv.
    Ergänzt eine (virtuelle) Spalte 'Teileinheit' anhand Mitarbeiter.csv.
    """
    EXTRA_COL = "Teileinheit"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_headers = list(ANWESENHEIT_HEADERS)
        # Wenn 'Teileinheit' noch nicht in CSV-Headern existiert, ergänzen wir sie nur in der Ansicht
        self.headers = list(self.base_headers)
        if self.EXTRA_COL not in self.headers:
            self.headers.append(self.EXTRA_COL)
        self.pn_to_te = _load_pn_to_te_map()
        self.rows: List[Dict[str, Any]] = []
        self.reload()

    # Basis
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.headers[section]
        if orientation == Qt.Vertical:
            return section + 1
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            r, c = index.row(), index.column()
            key = self.headers[c]
            if key == self.EXTRA_COL:
                pn = (self.rows[r].get("Personalnummer") or "").strip()
                return self.pn_to_te.get(pn, "")
            return self.rows[r].get(key, "")
        return None

    # Laden
    def reload(self):
        self.beginResetModel()
        self.pn_to_te = _load_pn_to_te_map()
        raw = read_csv_rows(ANWESENHEIT_CSV)
        # Stelle sicher, dass alle benötigten Keys existieren
        self.rows = [{h: r.get(h, "") for h in self.base_headers} for r in raw]
        self.endResetModel()


# ---------- Proxy: Filter PN, Teileinheit, Zeitraum ----------

class AttendanceFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pn_substr = ""
        self._te = ""          # leer = alle
        today = date.today()
        self._from = today
        self._to = today

    # Setters
    def set_pn_filter(self, text: str):
        self._pn_substr = (text or "").strip().lower()
        self.invalidateFilter()

    def set_te_filter(self, te: str):
        self._te = (te or "").strip()
        self.invalidateFilter()

    def set_date_range(self, d_from: date, d_to: date):
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        self._from, self._to = d_from, d_to
        self.invalidateFilter()

    # Filterlogik
    def filterAcceptsRow(self, source_row: int, parent: QModelIndex) -> bool:
        model: AttendanceModel = self.sourceModel()  # type: ignore

        # Datum prüfen
        try:
            col_date = model.headers.index("Datum")
            d_str = model.data(model.index(source_row, col_date), Qt.DisplayRole) or ""
            d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        except Exception:
            # ohne Datum nicht anzeigen
            return False
        if not (self._from <= d_obj <= self._to):
            return False

        # PN-Teilstring
        if self._pn_substr:
            try:
                col_pn = model.headers.index("Personalnummer")
                pn_val = (model.data(model.index(source_row, col_pn), Qt.DisplayRole) or "").lower()
            except ValueError:
                pn_val = ""
            if self._pn_substr not in pn_val:
                return False

        # Teileinheit (exakte Auswahl)
        if self._te:
            try:
                col_te = model.headers.index(AttendanceModel.EXTRA_COL)
                te_val = (model.data(model.index(source_row, col_te), Qt.DisplayRole) or "").strip()
            except ValueError:
                te_val = ""
            if te_val != self._te:
                return False

        return True


# ---------- Dialog mit Filterleiste (PN, Teileinheit, Zeitraum) + Schnellbuttons ----------

class AttendanceDialog(QDialog):
    """
    Links: Anwesenheitstabelle mit Filtern:
           - PN-Filter (Teilstring)
           - Teileinheit (Dropdown)
           - Zeitraum (Von/Bis) — Standard: heute→heute
    Rechts: Schnellbuttons „Kommen/Gehen“ (wirkt auf HEUTE) für alle markierten PNs.
    Zeiten werden nur gesetzt, wenn das Feld leer ist (kein Überschreiben).
    """
    KOMMEN_TIMES = ["06:00", "06:15", "06:30", "06:45", "07:00"]
    GEHEN_TIMES  = ["15:00", "15:15", "15:30", "15:45", "16:00"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Anwesenheit – {date.today().isoformat()}")

        # --- Filterleiste ---
        self.edPn = QLineEdit()
        self.edPn.setPlaceholderText("PN (Teilstring)…")

        self.cmbTe = QComboBox()
        self.cmbTe.addItem("Alle")  # leere Auswahl = alle
        for te in _collect_te_list():
            self.cmbTe.addItem(te)

        today_q = QDate.currentDate()
        self.dtFrom = QDateEdit(today_q)
        self.dtFrom.setCalendarPopup(True)
        self.dtFrom.setDisplayFormat("yyyy-MM-dd")

        self.dtTo = QDateEdit(today_q)
        self.dtTo.setCalendarPopup(True)
        self.dtTo.setDisplayFormat("yyyy-MM-dd")

        top = QHBoxLayout()
        top.addWidget(QLabel("PN:"))
        top.addWidget(self.edPn, 1)
        top.addSpacing(8)
        top.addWidget(QLabel("Teileinheit:"))
        top.addWidget(self.cmbTe)
        top.addSpacing(8)
        top.addWidget(QLabel("Von:"))
        top.addWidget(self.dtFrom)
        top.addWidget(QLabel("Bis:"))
        top.addWidget(self.dtTo)

        # --- Tabelle links ---
        self.model = AttendanceModel(self)
        self.proxy = AttendanceFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.resizeColumnsToContents()

        # --- rechts: Schnellbuttons ---
        right = QVBoxLayout()
        self.lblInfo = QLabel("Markiere links eine oder mehrere Zeilen. Buttons wirken auf HEUTE (füllt nur leere Felder).")
        right.addWidget(self.lblInfo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        cv = QVBoxLayout(container)

        gb_k = QGroupBox("Kommen")
        lv_k = QVBoxLayout(gb_k)
        for t in self.KOMMEN_TIMES:
            b = QPushButton(t)
            b.clicked.connect(lambda _=False, tt=t: self._apply_time(anfang=tt))
            lv_k.addWidget(b)
        cv.addWidget(gb_k)

        gb_g = QGroupBox("Gehen")
        lv_g = QVBoxLayout(gb_g)
        for t in self.GEHEN_TIMES:
            b = QPushButton(t)
            b.clicked.connect(lambda _=False, tt=t: self._apply_time(ende=tt))
            lv_g.addWidget(b)
        cv.addWidget(gb_g)

        cv.addStretch()
        scroll.setWidget(container)
        right.addWidget(scroll)

        # unten: schließen
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)

        # --- Layout gesamt ---
        main = QHBoxLayout()
        left = QVBoxLayout()
        left.addLayout(top)
        left.addWidget(self.table)
        main.addLayout(left, 3)
        main.addLayout(right, 2)

        outer = QVBoxLayout(self)
        outer.addLayout(main)
        outer.addLayout(bottom)
        self.setLayout(outer)
        self.resize(1200, 680)

        # --- Default-Filter: heute → heute ---
        self._apply_filters()  # stellt PN="", TE="Alle", From/To=today ein

        # --- Signals ---
        self.edPn.textChanged.connect(self._on_filter_changed)
        self.cmbTe.currentIndexChanged.connect(self._on_filter_changed)
        self.dtFrom.dateChanged.connect(self._on_filter_changed)
        self.dtTo.dateChanged.connect(self._on_filter_changed)
        self.table.selectionModel().selectionChanged.connect(self._update_info)

    # -------- Helpers / Slots --------

    def _on_filter_changed(self, *args):
        self._apply_filters()
        self.table.resizeColumnsToContents()
        self._update_info()

    def _apply_filters(self):
        # PN
        self.proxy.set_pn_filter(self.edPn.text())

        # TE
        te = self.cmbTe.currentText().strip()
        self.proxy.set_te_filter("" if te == "Alle" else te)

        # Zeitraum
        d_from = date(self.dtFrom.date().year(), self.dtFrom.date().month(), self.dtFrom.date().day())
        d_to   = date(self.dtTo.date().year(),   self.dtTo.date().month(),   self.dtTo.date().day())
        self.proxy.set_date_range(d_from, d_to)

    def _selected_personalnummern(self) -> List[str]:
        """PNs aus den markierten Zeilen (einmalig)."""
        pns: List[str] = []
        # Spalte PN finden
        try:
            col_pn = self.model.headers.index("Personalnummer")
        except ValueError:
            return pns

        for ix_proxy in self.table.selectionModel().selectedRows():
            ix_src = self.proxy.mapToSource(ix_proxy)
            pn = self.model.data(self.model.index(ix_src.row(), col_pn), Qt.DisplayRole)
            pn = (pn or "").strip()
            if pn and pn not in pns:
                pns.append(pn)
        return pns

    def _apply_time(self, anfang: Optional[str] = None, ende: Optional[str] = None):
        pns = self._selected_personalnummern()
        if not pns:
            persons = len(pns)
            QMessageBox.information(
                self,
                "Gespeichert",
                f"Gespeichert für {persons} Person{'en' if persons != 1 else ''}."
            )

            return

        today = date.today().isoformat()
        try:
            total_changed = 0
            total_skipped = 0
            for pn in pns:
                _ensure_today_row(pn)  # idempotent
                changed, skipped = _set_time_for_today(pn, anfang=anfang, ende=ende, overwrite=False)
                total_changed += changed
                total_skipped += skipped

            # Reload + visuelles Update
            self.model.reload()
            self.table.resizeColumnsToContents()
            self._update_info()

            what = f"Anfang = {anfang}" if anfang else f"Ende = {ende}"
            QMessageBox.information(
                self, "Gespeichert",
                f"{what} am {today} für {len(pns)} PN gesetzt.\n"
                f"• Felder gesetzt: {total_changed}\n"
                f"• Übersprungen (bereits belegt): {total_skipped}\n\n"
                f"Datei:\n{ANWESENHEIT_CSV}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Fehler beim Schreiben", str(e))

    def _update_info(self):
        count = len(self._selected_personalnummern())
        self.lblInfo.setText(
            f"Ausgewählte Zeilen: {count}  —  Buttons wirken auf HEUTE (nur leere Felder werden gefüllt)."
        )
