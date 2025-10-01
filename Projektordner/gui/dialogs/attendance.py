# gui/dialogs/attendance.py
from __future__ import annotations
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Tuple

from PySide6.QtCore import (
    Qt, QModelIndex, QAbstractTableModel, QSortFilterProxyModel, QDate, Signal
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView, QWidget,
    QPushButton, QLabel, QAbstractItemView, QMessageBox, QGroupBox,
    QScrollArea, QLineEdit, QComboBox, QDateEdit, QStyledItemDelegate,
    QHeaderView
)

from storage import (
    MITARBEITER_CSV,
    TEILEINHEITEN_CSV,
    ARBEITSZEITMODELLE_CSV,
    ANWESENHEIT_CSV, ANWESENHEIT_HEADERS,
    STATUS_CSV,
    read_csv_rows, write_csv_rows,
)
from logic import generate_attendance_for_person


# ---------- Helpers: Anwesenheit HEUTE idempotent setzen ----------

def _ensure_today_row(pn: str) -> None:
    generate_attendance_for_person(pn, path=ANWESENHEIT_CSV)


def _set_time_for_today(
    pn: str,
    anfang: Optional[str] = None,
    ende: Optional[str] = None,
    *,
    overwrite: bool = False,
) -> Tuple[int, int]:
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
        target_row["Status"] = "Anwesend"
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


# ---------- Stammdaten / Mappings ----------

def _load_pn_maps() -> tuple[
    Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]
]:
    """
    Liefert Mappings:
      - pn_to_te:   PN -> Teileinheit
      - pn_to_az:   PN -> Arbeitszeitmodell
      - pn_to_dg:   PN -> Dienstgrad
      - pn_to_vor:  PN -> Vorname
      - pn_to_nach: PN -> Nachname
    """
    mit_rows = read_csv_rows(MITARBEITER_CSV)

    pn_to_te: Dict[str, str] = {}
    pn_to_az: Dict[str, str] = {}
    pn_to_dg: Dict[str, str] = {}
    pn_to_vor: Dict[str, str] = {}
    pn_to_nach: Dict[str, str] = {}

    for r in mit_rows:
        pn = (r.get("Personalnummer") or "").strip()
        if not pn:
            continue
        pn_to_te[pn]   = (r.get("Teileinheit") or "").strip()
        pn_to_az[pn]   = (r.get("Arbeitszeitmodell") or "").strip()
        pn_to_dg[pn]   = (r.get("Dienstgrad") or "").strip()
        pn_to_vor[pn]  = (r.get("Vorname") or "").strip()
        pn_to_nach[pn] = (r.get("Nachname") or "").strip()

    return pn_to_te, pn_to_az, pn_to_dg, pn_to_vor, pn_to_nach


def _load_status_values() -> List[str]:
    vals: List[str] = []
    for r in read_csv_rows(STATUS_CSV):
        name = (r.get("Status") or "").strip()
        if name:
            vals.append(name)
    seen = set()
    out: List[str] = []
    for v in vals:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def _load_model_day_minutes() -> Dict[str, List[int]]:
    """arbeitszeitmodelle.csv → Modell -> [Mo..Fr] Minuten."""
    def to_min(s: str) -> int:
        try:
            return int(round(float((s or "0").replace(",", ".")) * 60))
        except Exception:
            return 0

    out: Dict[str, List[int]] = {}
    for r in read_csv_rows(ARBEITSZEITMODELLE_CSV):
        name = (r.get("Modell") or "").strip()
        if not name:
            continue
        daymins = [to_min(r.get(k, "")) for k in ("Mo", "Di", "Mi", "Do", "Fr")]
        out[name] = daymins
    return out


# ---------- Zeit/Format Utilities ----------

def _parse_hhmm(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _fmt_signed(mins: int) -> str:
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    return f"{sign}{mins//60}:{mins%60:02d}"


def _net_work_minutes(anf: str, end: str) -> Optional[int]:
    """
    Netto-Arbeitszeit mit „stehenden“ Pausenfenstern:
      - bis 6:00h zählt alles,
      - (6:00..6:30] Netto bleibt bei 6:00h stehen,
      - danach zählt es bis 9:00h weiter (mit 30 eingepreist),
      - (9:00..9:15] bleibt Netto bei 9:00h stehen,
      - danach zählt es weiter (insges. 45 min nicht gezählt).
    """
    a = _parse_hhmm(anf)
    b = _parse_hhmm(end)
    if a is None or b is None:
        return None
    if b < a:
        b += 24 * 60
    gross = b - a
    if gross <= 360:        # <= 6h
        return gross
    if gross <= 390:        # 6h..6:30h
        return 360
    gross_after_first = gross - 30
    if gross_after_first <= 540:  # <= 9h (nach erster Pause)
        return gross_after_first
    if gross_after_first <= 555:  # 9h..9:15h
        return 540
    return gross_after_first - 15


def _required_minutes_for(model_day_minutes: Dict[str, List[int]], pn_to_az: Dict[str, str], pn: str, d: date) -> int:
    wd = d.weekday()
    if wd >= 5:
        return 0
    model = pn_to_az.get(pn, "")
    if model and model in model_day_minutes:
        return model_day_minutes[model][wd] or 0
    # Fallback 9/9/9/9/5
    return 9 * 60 if wd <= 3 else 5 * 60


def _read_prev_cum_zk(rows: List[Dict[str, str]], pn: str, d: date) -> int:
    """Liest kumuliertes Zeitkonto (in Minuten) des Vortags für PN (0 wenn keiner)."""
    prev = None
    for r in rows:
        if (r.get("Personalnummer") or "").strip() != pn:
            continue
        try:
            rd = datetime.strptime(r.get("Datum", ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if rd < d:
            if (prev is None) or (rd > prev[0]):
                prev = (rd, r)
    if not prev:
        return 0
    zk = (prev[1].get("Zeitkonto") or "").strip()
    if not zk:
        return 0
    try:
        sgn = 1
        if zk.startswith("-"):
            sgn = -1
            zk = zk[1:]
        if zk.startswith("+"):
            zk = zk[1:]
        h, m = zk.split(":")
        return sgn * (int(h) * 60 + int(m))
    except Exception:
        return 0


# ---------- Delegates ----------

class StatusDelegate(QStyledItemDelegate):
    def __init__(self, values: List[str], parent=None):
        super().__init__(parent)
        self._values = values

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        for v in self._values:
            cb.addItem(v)
        cb.setStyleSheet(
            "QComboBox { background: #f0f0f0; color: black; } "
            "QAbstractItemView { background: #f0f0f0; color: black; }"
        )
        return cb

    def setEditorData(self, editor: QComboBox, index):
        cur = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        i = editor.findText(cur)
        if i >= 0:
            editor.setCurrentIndex(i)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)


# ---------- Model ----------

class AttendanceModel(QAbstractTableModel):
    modelReset = Signal()  # für Delegate-Installation

    # Anzeige-Spalten (aus Mitarbeiter.csv)
    EXTRA_TE = "Teileinheit"
    EXTRA_AZ = "Arbeitszeitmodell"
    EXTRA_DG = "Dienstgrad"
    EXTRA_VOR = "Vorname"
    EXTRA_NACH = "Nachname"

    EDITABLE_COLUMNS = {"Status", "Anfang", "Ende", "Zeitkonto", "Urlaub", "Mehrarbeit", "FvD"}

    def __init__(self, parent=None):
        super().__init__(parent)

        # CSV-Basisheader
        self.base_headers = list(ANWESENHEIT_HEADERS)

        # Feste Reihenfolge für die Anzeige:
        self.headers = [
            "Personalnummer",
            "Vorname",
            "Nachname",
            "Dienstgrad",
            "Status",
            "Datum",
            "Anfang",
            "Ende",
            "Zeitkonto",
            "Urlaub",
            "Mehrarbeit",
            "FvD",
            "Arbeitszeitmodell",
            "Teileinheit",
        ]

        # Daten/Mappings
        self.rows: List[Dict[str, Any]] = []
        self.pn_to_te: Dict[str, str] = {}
        self.pn_to_az: Dict[str, str] = {}
        self.pn_to_dg: Dict[str, str] = {}
        self.pn_to_vor: Dict[str, str] = {}
        self.pn_to_nach: Dict[str, str] = {}
        self.status_values: List[str] = []
        self.model_day_minutes: Dict[str, List[int]] = {}
        self.reload()

    def rowCount(self, parent=QModelIndex()) -> int: return 0 if parent.isValid() else len(self.rows)
    def columnCount(self, parent=QModelIndex()) -> int: return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole: return None
        if orientation == Qt.Horizontal: return self.headers[section]
        if orientation == Qt.Vertical: return section + 1
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        key = self.headers[index.column()]
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if key in self.EDITABLE_COLUMNS:
            return base | Qt.ItemIsEditable
        return base

    def _validate_time(self, s: str) -> bool:
        if not s: return True
        parts = s.split(":")
        if len(parts) != 2: return False
        try:
            hh = int(parts[0]); mm = int(parts[1])
            return 0 <= hh <= 23 and 0 <= mm <= 59
        except Exception:
            return False

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid(): return None
        r, c = index.row(), index.column()
        key = self.headers[c]

        # Basisfelder kommen aus self.rows (CSV)
        if key in self.base_headers:
            if key == "Datum":
                raw = self.rows[r].get("Datum", "")
                if role == Qt.DisplayRole:
                    try:
                        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d.%m.%Y")
                    except Exception:
                        return raw
                if role == Qt.EditRole:
                    return raw
            if role in (Qt.DisplayRole, Qt.EditRole):
                if key == "Status":
                    v = (self.rows[r].get(key) or "").strip()
                    return v if v else "Anwesend"
                return self.rows[r].get(key, "")
            return None

        # Extra-Felder kommen aus Mappings per PN
        pn = (self.rows[r].get("Personalnummer") or "").strip()
        if key == self.EXTRA_VOR and role in (Qt.DisplayRole, Qt.EditRole):
            return self.pn_to_vor.get(pn, "")
        if key == self.EXTRA_NACH and role in (Qt.DisplayRole, Qt.EditRole):
            return self.pn_to_nach.get(pn, "")
        if key == self.EXTRA_DG and role in (Qt.DisplayRole, Qt.EditRole):
            return self.pn_to_dg.get(pn, "")
        if key == self.EXTRA_AZ and role in (Qt.DisplayRole, Qt.EditRole):
            return self.pn_to_az.get(pn, "")
        if key == self.EXTRA_TE and role in (Qt.DisplayRole, Qt.EditRole):
            return self.pn_to_te.get(pn, "")

        return None

    # --- Kernrechner & konsistente Neuberechnung ---

    def _recalc_time_account_for_row(self, r: int) -> None:
        """ZK(neu) = ZK(vortag) + (Netto - Soll)  (nur wenn Anfang & Ende vorhanden)."""
        row = self.rows[r]
        pn = (row.get("Personalnummer") or "").strip()
        try:
            d = datetime.strptime(row.get("Datum", ""), "%Y-%m-%d").date()
        except Exception:
            return

        net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", ""))
        if net is None:
            return

        req = _required_minutes_for(self.model_day_minutes, self.pn_to_az, pn, d)
        prev = _read_prev_cum_zk(self.rows, pn, d)
        new_sum = prev + (net - req)
        row["Zeitkonto"] = _fmt_signed(new_sum)

    def _apply_status_automation(self, r: int, status_val: str) -> None:
        """Setzt Zähler/Basiseffekte bei Statuswechsel (Urlaub/FvD/Zeitausgleich/Mehrarbeit/Abbau Mehrarbeit)."""
        row = self.rows[r]
        pn = (row.get("Personalnummer") or "").strip()
        try:
            d = datetime.strptime(row.get("Datum", ""), "%Y-%m-%d").date()
        except Exception:
            d = date.today()

        s = (status_val or "").strip().lower()
        req = _required_minutes_for(self.model_day_minutes, self.pn_to_az, pn, d)

        # Tageszähler
        if s == "urlaub":
            row["Urlaub"] = "-1"
        elif s == "fvd":
            row["FvD"] = "-1"

        # Mehrarbeit/Abbau als Sofort-Effekt vorbereiten (ZK wird in _recompute_row konsistent gesetzt)
        if s == "mehrarbeit":
            net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", "")) or 0
            over = max(0, net - req)
            row["Mehrarbeit"] = _fmt_signed(over) if over != 0 else "+0:00"
        elif s in ("abbau mehrarbeit", "abbau_mehrarbeit"):
            row["Mehrarbeit"] = _fmt_signed(-req)

    def _recompute_row(self, r: int) -> None:
        """
        Konsistente Neuberechnung für Zeile r:
          - setzt Zähler gemäß Status (Urlaub/FvD),
          - berechnet 'Zeitkonto' abhängig von Status/Anfang/Ende,
          - aktualisiert 'Mehrarbeit' bei Status=Mehrarbeit.
        """
        row = self.rows[r]
        pn = (row.get("Personalnummer") or "").strip()
        try:
            d = datetime.strptime(row.get("Datum", ""), "%Y-%m-%d").date()
        except Exception:
            return

        status = (row.get("Status") or "").strip().lower()
        req = _required_minutes_for(self.model_day_minutes, self.pn_to_az, pn, d)
        prev = _read_prev_cum_zk(self.rows, pn, d)

        # Tageszähler (Urlaub/FvD) gemäß Status
        if status == "urlaub":
            row["Urlaub"] = "-1"
        elif status == "fvd":
            row["FvD"] = "-1"

        # Zeitkonto/Mehrarbeit je Status
        if status == "zeitausgleich":
            row["Zeitkonto"] = _fmt_signed(prev - req)
        elif status == "mehrarbeit":
            net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", "")) or 0
            over = max(0, net - req)
            row["Mehrarbeit"] = _fmt_signed(over) if over != 0 else "+0:00"
            row["Zeitkonto"] = _fmt_signed(prev + (net - req))
        elif status in ("abbau mehrarbeit", "abbau_mehrarbeit"):
            row["Mehrarbeit"] = _fmt_signed(-req)
            net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", ""))
            if net is not None:
                row["Zeitkonto"] = _fmt_signed(prev + (net - req))
        else:
            net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", ""))
            if net is not None:
                row["Zeitkonto"] = _fmt_signed(prev + (net - req))

    # --- Editieren ---

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False
        r, c = index.row(), index.column()
        key = self.headers[c]
        val = str(value or "").strip()

        # Nur echte CSV-Felder sind bearbeitbar/speicherbar
        if key not in self.EDITABLE_COLUMNS:
            return False

        # Zeit-Validierung
        if key in ("Anfang", "Ende") and not self._validate_time(val):
            return False

        # Leerer Status -> "Anwesend" als Default
        if key == "Status" and not val:
            val = "Anwesend"

        # Setzen (nur Basisfelder)
        if key in self.base_headers:
            self.rows[r][key] = val
        else:
            return False  # Anzeige-/Extra-Felder sind read-only

        # Reaktionslogik: Immer konsistente Neuberechnung nach Status/Anfang/Ende
        if key in ("Status", "Anfang", "Ende"):
            if key == "Status":
                self._apply_status_automation(r, val)
            self._recompute_row(r)

        # Persistenz
        try:
            write_csv_rows(ANWESENHEIT_CSV, self.rows, self.base_headers)
        except Exception:
            pass

        # UI aktualisieren (abhängige Felder mit anstoßen)
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        for colname in ("Zeitkonto", "Urlaub", "Mehrarbeit", "FvD"):
            try:
                cc = self.headers.index(colname)
                self.dataChanged.emit(self.index(r, cc), self.index(r, cc), [Qt.DisplayRole, Qt.EditRole])
            except Exception:
                pass

        return True

    def reload(self):
        self.beginResetModel()
        base = read_csv_rows(ANWESENHEIT_CSV)
        self.rows = []
        for r in base:
            row = {h: r.get(h, "") for h in self.base_headers}
            if not (row.get("Status") or "").strip():
                row["Status"] = "Anwesend"
            self.rows.append(row)

        self.pn_to_te, self.pn_to_az, self.pn_to_dg, self.pn_to_vor, self.pn_to_nach = _load_pn_maps()
        self.status_values = _load_status_values()
        self.model_day_minutes = _load_model_day_minutes()
        self.endResetModel()
        self.modelReset.emit()  # damit der Dialog seinen Delegate setzen kann


# ---------- Proxy (Filter) ----------

class AttendanceFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pn_substr = ""
        self._te = ""
        today = date.today()
        self._from = today
        self._to = today

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

    def filterAcceptsRow(self, source_row: int, parent: QModelIndex) -> bool:
        model: AttendanceModel = self.sourceModel()  # type: ignore
        # Datum
        try:
            col_date = model.headers.index("Datum")
            d_str = model.data(model.index(source_row, col_date), Qt.EditRole) or ""
            d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        except Exception:
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

        # Teileinheit
        if self._te:
            try:
                col_te = model.headers.index(AttendanceModel.EXTRA_TE)
                te_val = (model.data(model.index(source_row, col_te), Qt.DisplayRole) or "").strip()
            except ValueError:
                te_val = ""
            if te_val != self._te:
                return False

        return True


# ---------- Dialog ----------

class AttendanceDialog(QDialog):
    """
    Links: Tabelle (Filter PN/Teileinheit/Zeitraum).
    Rechts: Schnellbuttons „Kommen/Gehen“ (wirkt auf HEUTE) für markierte PNs.
    """
    KOMMEN_TIMES = ["06:00", "06:15", "06:30", "06:45", "07:00"]
    GEHEN_TIMES  = ["15:00", "15:15", "15:30", "15:45", "16:00"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Anwesenheit – {date.today().strftime('%d.%m.%Y')}")

        # --- Filterleiste ---
        self.edPn = QLineEdit(); self.edPn.setPlaceholderText("PN (Teilstring)…")
        self.cmbTe = QComboBox(); self.cmbTe.addItem("Alle")
        for te in self._collect_te_list(): self.cmbTe.addItem(te)

        today_q = QDate.currentDate()
        self.dtFrom = QDateEdit(today_q); self.dtFrom.setCalendarPopup(True); self.dtFrom.setDisplayFormat("dd.MM.yyyy")
        self.dtTo   = QDateEdit(today_q); self.dtTo.setCalendarPopup(True);   self.dtTo.setDisplayFormat("dd.MM.yyyy")

        top = QHBoxLayout()
        top.addWidget(QLabel("PN:")); top.addWidget(self.edPn, 1); top.addSpacing(8)
        top.addWidget(QLabel("Teileinheit:")); top.addWidget(self.cmbTe); top.addSpacing(8)
        top.addWidget(QLabel("Von:")); top.addWidget(self.dtFrom)
        top.addWidget(QLabel("Bis:")); top.addWidget(self.dtTo)

        # --- Tabelle links ---
        self.model = AttendanceModel(self)
        self.proxy = AttendanceFilterProxy(self); self.proxy.setSourceModel(self.model)
        self.table = QTableView(); self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )

        # Spaltenbreiten/Resize
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(24)

        # Mindestbreite für "Teileinheit"
        try:
            te_src = self.model.headers.index("Teileinheit")
            te_view = te_src if self.model.rowCount() == 0 else self.proxy.mapFromSource(self.model.index(0, te_src)).column()
            self.table.horizontalHeader().setMinimumSectionSize(40)
            self.table.setColumnWidth(te_view, 140)
            self.table.horizontalHeader().setSectionResizeMode(te_view, QHeaderView.Interactive)
        except Exception:
            pass

        # --- rechts: Schnellbuttons ---
        right = QVBoxLayout()
        self.lblInfo = QLabel("Ausgewählte Zeilen: 0 — Buttons wirken auf HEUTE (füllt nur leere Felder).")
        right.addWidget(self.lblInfo)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        container = QWidget(); cv = QVBoxLayout(container)

        gb_k = QGroupBox("Kommen"); lv_k = QVBoxLayout(gb_k)
        for t in self.KOMMEN_TIMES:
            b = QPushButton(t); b.clicked.connect(lambda _=False, tt=t: self._apply_time(anfang=tt))
            lv_k.addWidget(b)
        cv.addWidget(gb_k)

        gb_g = QGroupBox("Gehen"); lv_g = QVBoxLayout(gb_g)
        for t in self.GEHEN_TIMES:
            b = QPushButton(t); b.clicked.connect(lambda _=False, tt=t: self._apply_time(ende=tt))
            lv_g.addWidget(b)
        cv.addWidget(gb_g)

        cv.addStretch()
        scroll.setWidget(container)
        right.addWidget(scroll)

        # unten: schließen
        bottom = QHBoxLayout(); bottom.addStretch()
        btn_close = QPushButton("Schließen"); btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)

        # --- Layout & Größe ---
        left = QVBoxLayout(); left.addLayout(top); left.addWidget(self.table)
        main = QHBoxLayout(); main.addLayout(left, 3); main.addLayout(right, 2)
        outer = QVBoxLayout(self); outer.addLayout(main); outer.addLayout(bottom)

        self.resize(1600, 950)
        self.table.setMinimumWidth(1200)

        # --- Default-Filter: heute ---
        self._apply_filters()

        # --- Signals ---
        self.edPn.textChanged.connect(self._on_filter_changed)
        self.cmbTe.currentIndexChanged.connect(self._on_filter_changed)
        self.dtFrom.dateChanged.connect(self._on_filter_changed)
        self.dtTo.dateChanged.connect(self._on_filter_changed)
        self.table.selectionModel().selectionChanged.connect(self._update_info)

        # Status-Delegate sicher installieren, auch wenn 0 Zeilen
        self.model.modelReset.connect(self._install_status_delegate)
        self._install_status_delegate()

        # Bootstrap: wenn im Filterbereich nichts sichtbar ist, heutige Zeilen je PN anlegen
        self._bootstrap_today_rows_if_empty()

    # -------- Helpers / Slots --------

    def _install_status_delegate(self):
        """Installiert den Status-Delegate robust über den Proxy."""
        try:
            col_status_src = self.model.headers.index("Status")
            if self.model.rowCount() > 0:
                any_proxy_ix = self.proxy.mapFromSource(self.model.index(0, col_status_src))
                col_status = any_proxy_ix.column()
            else:
                col_status = col_status_src
            self.table.setItemDelegateForColumn(col_status, StatusDelegate(self.model.status_values, self.table))
        except Exception:
            pass

    def _collect_te_list(self) -> List[str]:
        rows = read_csv_rows(TEILEINHEITEN_CSV)
        vals = []
        for r in rows:
            if r:
                vals.append(next(iter(r.values())))
        return sorted({(v or "").strip() for v in vals if v and v.strip()})

    def _qdate_to_py(self, qd: QDate) -> date:
        return date(qd.year(), qd.month(), qd.day())

    def _apply_filters(self):
        self.proxy.set_pn_filter(self.edPn.text())
        te = self.cmbTe.currentText().strip()
        self.proxy.set_te_filter("" if te == "Alle" else te)
        self.proxy.set_date_range(self._qdate_to_py(self.dtFrom.date()), self._qdate_to_py(self.dtTo.date()))

    def _on_filter_changed(self, *args):
        self._apply_filters()
        self.table.resizeColumnsToContents()
        # falls leer, heutige Zeilen erzeugen
        self._bootstrap_today_rows_if_empty()

    def _bootstrap_today_rows_if_empty(self):
        """Erzeuge für HEUTE je Mitarbeiter eine Anwesenheitszeile (Status=Anwesend), falls im Filter-Zeitraum nichts angezeigt wird."""
        if self.proxy.rowCount() > 0:
            return
        # Alle PNs aus Mitarbeiter.csv holen
        mit = read_csv_rows(MITARBEITER_CSV)
        pns = [(r.get("Personalnummer") or "").strip() for r in mit]
        pns = [pn for pn in pns if pn]
        if not pns:
            return
        # Für jede PN heutige Zeile sicherstellen
        for pn in pns:
            _ensure_today_row(pn)
        # Neu laden & Filter erneut anwenden
        self.model.reload()
        self._apply_filters()

    def _selected_personalnummern(self) -> List[str]:
        pns: List[str] = []
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
            QMessageBox.information(self, "Hinweis", "Bitte links eine oder mehrere Zeilen markieren (Strg/Shift).")
            return

        try:
            # 1) Heute-Zeile anlegen (falls fehlt) und Anfang/Ende setzen
            for pn in pns:
                _ensure_today_row(pn)
                _set_time_for_today(pn, anfang=anfang, ende=ende, overwrite=False)

            # 2) Model neu laden → aktuelle Daten + Mappings im RAM
            self.model.reload()

            # 3) Zeitkonto für HEUTE je PN kumuliert berechnen und zurückschreiben
            today = date.today()
            changed_any = False

            for pn in pns:
                # passende Zeile (PN, HEUTE) suchen
                idx = -1
                for i, row in enumerate(self.model.rows):
                    if (row.get("Personalnummer") or "").strip() != pn:
                        continue
                    try:
                        rd = datetime.strptime(row.get("Datum", ""), "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if rd == today:
                        idx = i
                        break
                if idx < 0:
                    continue

                row = self.model.rows[idx]
                old_zk = (row.get("Zeitkonto") or "").strip()
                status = (row.get("Status") or "").strip().lower()

                # Tages-Soll aus Arbeitszeitmodell
                req = _required_minutes_for(self.model.model_day_minutes, self.model.pn_to_az, pn, today)
                # kumuliertes Zeitkonto vom Vortag
                prev = _read_prev_cum_zk(self.model.rows, pn, today)

                # Sonderfall: Zeitausgleich → ZK = prev - Soll
                if status == "zeitausgleich":
                    new_zk = _fmt_signed(prev - req)
                    if new_zk != old_zk:
                        row["Zeitkonto"] = new_zk
                        changed_any = True
                else:
                    # Normalfall: nur wenn Anfang & Ende vorhanden → ZK = prev + (Netto - Soll)
                    net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", ""))
                    if net is not None:
                        new_zk = _fmt_signed(prev + (net - req))
                        if new_zk != old_zk:
                            row["Zeitkonto"] = new_zk
                            changed_any = True

                # Status-Automationen für Zähler/Konten (Urlaub/FvD/Mehrarbeit/Abbau) anwenden
                if status == "urlaub":
                    row["Urlaub"] = "-1"
                if status == "fvd":
                    row["FvD"] = "-1"
                if status == "mehrarbeit":
                    net = _net_work_minutes(row.get("Anfang", ""), row.get("Ende", "")) or 0
                    over = max(0, net - req)
                    row["Mehrarbeit"] = _fmt_signed(over) if over != 0 else "+0:00"
                if status in ("abbau mehrarbeit", "abbau_mehrarbeit"):
                    row["Mehrarbeit"] = _fmt_signed(-req)

            if changed_any:
                # 4) Persistieren
                write_csv_rows(ANWESENHEIT_CSV, self.model.rows, self.model.base_headers)

            # 5) Anzeige auffrischen
            self.model.reload()
            self.table.resizeColumnsToContents()
            self._update_info()

            persons = len(pns)
            QMessageBox.information(self, "Gespeichert",
                                    f"Gespeichert für {persons} Person{'en' if persons != 1 else ''}.")

        except Exception as e:
            QMessageBox.critical(self, "Fehler beim Schreiben", str(e))

    def _update_info(self):
        count = len(self._selected_personalnummern())
        self.lblInfo.setText(f"Ausgewählte Zeilen: {count} — Buttons wirken auf HEUTE (nur leere Felder werden gefüllt).")
