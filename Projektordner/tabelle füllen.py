import csv
from datetime import date, timedelta

def seed_zeitkonten(dateiname="zeitkonten.csv"):
    # Ein paar Einträge pro Mitarbeiter
    startdatum = date(2025, 9, 1)
    daten = []

    for i, pn in enumerate(["1001", "1002", "1003", "1004"], start=0):
        for tag in range(5):  # 5 Arbeitstage
            datum = startdatum + timedelta(days=tag)
            daten.append({
                "Personalnummer": pn,
                "Datum": datum.isoformat(),
                "Sollstunden": 8 if pn in ("1001", "1004") else 4,
                "Iststunden": 8 if tag != 2 else (6 if pn == "1002" else 4),
                "Bemerkung": "OK" if tag != 2 else "Fehlzeit/kurz"
            })

    with open(dateiname, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=daten[0].keys())
        writer.writeheader()
        writer.writerows(daten)

if __name__ == "__main__":
    seed_zeitkonten()
    print("zeitkonten.csv erfolgreich erstellt!")
