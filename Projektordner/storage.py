"""
Storage-/CSV-Schicht für PersonalPrinz.

- Pfade & Headerkonstanten
- CSV I/O (lesen/schreiben, ensure-Funktionen)
- Keine Abhängigkeit zu `logic.py` (wichtig gegen Zyklen)
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List

# Basisverzeichnis und Datenordner
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

# -------- CSV Hilfen --------


def ensure_file_with_header(path: Path, header: List[str]) -> None:
    """Erzeuge Datei mit nur Header, falls fehlt/leer (idempotent)."""
    if not path.exists() or path.stat().st_size == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def ensure_all_csvs() -> None:
    """Alle projektrelevanten CSVs mit korrekten Headern anlegen (idempotent)."""
    ensure_file_with_header(MITARBEITER_CSV, MITARBEITER_HEADERS)
    ensure_file_with_header(DIENSTGRADE_CSV, ["Dienstgrad"])
    ensure_file_with_header(TEILEINHEITEN_CSV, ["Teileinheit"])
    ensure_file_with_header(ANWESENHEIT_CSV, ANWESENHEIT_HEADERS)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """CSV als Liste von Dicts lesen (robust, utf-8-sig, leer → [])."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        content = f.read()
    if not content.strip():
        return []
    import io
    import csv as _csv

    reader = _csv.DictReader(io.StringIO(content))
    return [{k: (v or "") for k, v in r.items()} for r in reader]


def write_csv_rows(path: Path, rows: List[Dict[str, str]], headers: List[str]) -> None:
    """Dict-Zeilen atomar schreiben (erst .tmp, dann ersetzen)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({h: (r.get(h, "") or "") for h in headers})
    tmp.replace(path)


def read_single_column_values(path: Path, colname: str) -> List[str]:
    """Eindeutige, nicht-leere Werte einer Spalte (Reihenfolge: first-seen)."""
    vals: List[str] = []
    for r in read_csv_rows(path):
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
    """Einspalten-CSV schreiben."""
    write_csv_rows(path, [{colname: v} for v in values], [colname])
