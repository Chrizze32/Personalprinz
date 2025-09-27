"""
Fachlogik für PersonalPrinz (GUI-frei, mit Doctests).

- Nutzt ausschließlich die Storage-Schicht (storage.py).
- Keine Abhängigkeit von PySide6 oder GUI.

Doctests ausführen:
    pytest -q --doctest-modules logic.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Für Laufzeitlogik: wir nutzen storage direkt
from storage import (
    ANWESENHEIT_CSV,
    ANWESENHEIT_HEADERS,
    read_csv_rows,
    write_csv_rows,
)


def generate_attendance_for_person(pn: str, path: Optional[Path] = None) -> None:
    """Erzeuge fehlende Anwesenheitseinträge (heute..Jahresende) für eine PN (idempotent).

    Args:
        pn: Achtstellige Personalnummer.
        path: Optionale Zieldatei für Tests; Standard ist :data:`storage.ANWESENHEIT_CSV`.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> from storage import ensure_file_with_header, ANWESENHEIT_HEADERS
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
    """Entferne sämtliche Anwesenheitszeilen für eine Personalnummer.

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> from storage import ensure_file_with_header, ANWESENHEIT_HEADERS
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


def is_valid_pn(pn: str) -> bool:
    """Prüft, ob eine Personalnummer aus exakt 8 Ziffern besteht.

    Examples:
        >>> is_valid_pn("00001234")
        True
        >>> is_valid_pn("1234567")
        False
        >>> is_valid_pn("12A45678")
        False
    """
    return len(pn) == 8 and pn.isdigit()


def normalize_name(s: str) -> str:
    """Trimmt Leerzeichen, reduziert Mehrfach-Leerzeichen auf eins und wendet Title-Case an.

    Examples:
        >>> normalize_name("  müLLer   meier ")
        'Müller Meier'
    """
    s = " ".join((s or "").split())
    return s.title()
