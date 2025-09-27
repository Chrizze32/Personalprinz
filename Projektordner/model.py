"""
Domänenmodelle für PersonalPrinz.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Mitarbeiter:
    personalnummer: str
    nachname: str
    vorname: str
    arbeitszeitmodell: str
    dienstgrad: str
    teileinheit: str


@dataclass
class Anwesenheit:
    personalnummer: str
    datum: str  # ISO-YYYY-MM-DD
    status: str = ""
    anfang: str = ""
    ende: str = ""
    zeitkonto: str = ""
    urlaub: str = ""
    mehrarbeit: str = ""
    fvd: str = ""
