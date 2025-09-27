"""Dialog-Sammlung für PersonalPrinz (lazy exports, damit keine Kreisimporte knallen)."""

__all__ = ["MitarbeiterDialog", "AttendanceDialog", "SingleListDialog"]

def __getattr__(name: str):
    if name == "MitarbeiterDialog":
        from .mitarbeiter import MitarbeiterDialog
        return MitarbeiterDialog
    if name == "AttendanceDialog":
        from .attendance import AttendanceDialog
        return AttendanceDialog
    if name == "SingleListDialog":
        from .single_list import SingleListDialog
        return SingleListDialog
    raise AttributeError(name)
