"""
Logik- und CSV-Helfer für PersonalPrinz.

Dieses Modul ist GUI-frei und damit gut testbar.
Doctests kannst du so laufen lassen:

    pytest -q --doctest-modules logic.py
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Basisordner (liegt bei dir direkt im Projektordner)
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# CSV-Pfade
MITARBEITER_CSV = DATA_DIR / "Mitarbeiter.csv"
DIENSTGRADE_CSV = DATA_DIR / "Dienstgrade.csv"
TEILEINHEITEN_CSV = DATA_DIR / "Teileinheiten.csv"
ANWESENHEIT_CSV = DATA_DIR / "Anwesenheit.csv"

# Header
MITARBEITER_HEADERS = [
    "Personalnummer",
    "Nachname",
    "Vorname",
    "Arbeitszeitmodell",
    "Dienstgrad",
    "Teileinheit",
]
ANWESENHEIT_HEADERS = [
    "Personalnummer",
    "Datum",
    "Status",
    "Anfang",
    "Ende",
    "Zeitkonto",
    "Urlaub",
    "Mehrarbeit",
    "FvD",
]


def ensure_file_with_header(path: Path, header: List[str]) -> None:
    """
    Falls Datei fehlt/leer ist: schreibe nur den Header.

    Args:
        path: Zielpfad der CSV-Datei.
        header: Spaltenüberschriften in gewünschter Reihenfolge.

    Examples:
        >>> # legt eine neue Datei mit Header an
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_hdr.csv"
        >>> _ = tmp.unlink(missing_ok=True)
        >>> ensure_file_with_header(tmp, ["A", "B"])
        >>> tmp.read_text(encoding="utf-8").splitlines()[0]
        'A,B'
    """
    if not path.exists() or path.stat().st_size == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)


def ensure_all_csvs() -> None:
    """Lege alle projektrelevanten CSV-Dateien mit korrekten Headern an (idempotent)."""
    ensure_file_with_header(MITARBEITER_CSV, MITARBEITER_HEADERS)
    ensure_file_with_header(DIENSTGRADE_CSV, ["Dienstgrad"])
    ensure_file_with_header(TEILEINHEITEN_CSV, ["Teileinheit"])
    ensure_file_with_header(ANWESENHEIT_CSV, ANWESENHEIT_HEADERS)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """
    Lese CSV als Liste von Dicts (Spaltenname → Wert). Handhabt UTF-8-BOM und leere Dateien.

    Args:
        path: Pfad zur CSV-Datei.

    Returns:
        Liste von Zeilen als Dicts. Bei fehlender/leerere Datei: [].

    Examples:
        >>> from pathlib import Path
        >>> import tempfile, csv as _csv
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_read.csv"
        >>> with tmp.open("w", newline="", encoding="utf-8") as f:
        ...     w = _csv.writer(f)
        ...     _ = w.writerow(["A","B"])
        ...     _ = w.writerow(["1","2"])
        >>> read_csv_rows(tmp)
        [{'A': '1', 'B': '2'}]
    """
    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        content = f.read()

    if not content.strip():
        return []

    import io

    reader = csv.DictReader(io.StringIO(content))
    return [{k: (v or "") for k, v in r.items()} for r in reader]


def write_csv_rows(path: Path, rows: List[Dict[str, str]], headers: List[str]) -> None:
    """
    Schreibe Dict-Zeilen sicher in eine CSV-Datei mit vorgegebener Header-Reihenfolge.

    Es wird zuerst in eine temporäre Datei geschrieben und danach atomar ersetzt.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_write.csv"
        >>> rows = [{"A":"1","B":"2"}, {"A":"3","B":"4"}]
        >>> write_csv_rows(tmp, rows, ["A","B"])
        >>> read_csv_rows(tmp)
        [{'A': '1', 'B': '2'}, {'A': '3', 'B': '4'}]
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: (r.get(h, "") or "") for h in headers})
    tmp.replace(path)


def read_single_column_values(path: Path, colname: str) -> List[str]:
    """
    Lese eine Spalte aus CSV und liefere eindeutige, nicht-leere Werte.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_single.csv"
        >>> write_csv_rows(tmp, [{"X":"a"},{"X":"b"},{"X":"a"},{"X":""}], ["X"])
        >>> read_single_column_values(tmp, "X")
        ['a', 'b']
    """
    rows = read_csv_rows(path)
    vals: List[str] = []
    for r in rows:
        v = (r.get(colname) or "").strip()
        if v:
            vals.append(v)

    seen = set()
    out: List[str] = []
    for v in vals:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def write_single_column_values(path: Path, colname: str, values: List[str]) -> None:
    """
    Schreibe Werte in eine Einspalten-CSV.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_write_single.csv"
        >>> write_single_column_values(tmp, "X", ["a","b"])
        >>> read_single_column_values(tmp, "X")
        ['a', 'b']
    """
    rows = [{colname: v} for v in values]
    write_csv_rows(path, rows, [colname])


def generate_attendance_for_person(pn: str, path: Optional[Path] = None) -> None:
    """
    Erzeuge fehlende Anwesenheitstage (heute..Jahresende) für eine PN (idempotent).

    Args:
        pn: Achtstellige Personalnummer.
        path: Optionaler Zielpfad für Tests; Standard ist ANWESENHEIT_CSV.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_att.csv"
        >>> ensure_file_with_header(tmp, ANWESENHEIT_HEADERS)
        >>> generate_attendance_for_person("00001234", path=tmp)
        >>> rows = read_csv_rows(tmp)
        >>> any(r["Personalnummer"] == "00001234" for r in rows)
        True
        >>> # idempotent: zweiter Aufruf erzeugt keine Duplikate
        >>> n1 = len(rows)
        >>> generate_attendance_for_person("00001234", path=tmp)
        >>> len(read_csv_rows(tmp)) == n1
        True
    """
    target = path or ANWESENHEIT_CSV

    today = date.today()
    year_end = date(today.year, 12, 31)

    existing = read_csv_rows(target)
    exists_set = {(r.get("Personalnummer", ""), r.get("Datum", "")) for r in existing}

    add_rows: List[Dict[str, str]] = []
    d = today
    while d <= year_end:
        key = (pn, d.isoformat())
        if key not in exists_set:
            add_rows.append(
                {
                    "Personalnummer": pn,
                    "Datum": d.isoformat(),
                    "Status": "",
                    "Anfang": "",
                    "Ende": "",
                    "Zeitkonto": "",
                    "Urlaub": "",
                    "Mehrarbeit": "",
                    "FvD": "",
                }
            )
        d += timedelta(days=1)

    if add_rows:
        existing.extend(add_rows)
        existing.sort(key=lambda r: (r.get("Personalnummer", ""), r.get("Datum", "")))
        write_csv_rows(target, existing, ANWESENHEIT_HEADERS)


def remove_attendance_for_person(pn: str, path: Optional[Path] = None) -> None:
    """
    Entferne sämtliche Anwesenheitszeilen für eine Personalnummer.

    Args:
        pn: Achtstellige Personalnummer.
        path: Optionaler Zielpfad für Tests; Standard ist ANWESENHEIT_CSV.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.gettempdir()) / "pp_demo_att_remove.csv"
        >>> ensure_file_with_header(tmp, ANWESENHEIT_HEADERS)
        >>> generate_attendance_for_person("00000001", path=tmp)
        >>> remove_attendance_for_person("00000001", path=tmp)
        >>> all(r["Personalnummer"] != "00000001" for r in read_csv_rows(tmp))
        True
    """
    target = path or ANWESENHEIT_CSV
    rows = read_csv_rows(target)
    filtered = [r for r in rows if r.get("Personalnummer") != pn]
    if len(filtered) != len(rows):
        write_csv_rows(target, filtered, ANWESENHEIT_HEADERS)
