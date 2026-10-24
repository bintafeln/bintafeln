"""Historie eines Haushalts (ADR 0031): was sich wann geändert hat.

Verglichen werden Schnappschüsse vor und nach einer Änderung, gleich ob sie aus einem Import, der
Aufnahme eines Antrags oder der Bearbeitung durch den Admin kommt. Festgehalten wird nur, was das
Fachkonzept nennt: neu, Status, Kundengruppe, Ausweis gültig bis, Personen hinzu oder entfallen.
"""

import datetime as dt

from django.db.models import Prefetch

from apps.kunden.models import Haushalt, HaushaltEreignis, Person


def _datum(wert: dt.date | None) -> str:
    return f"{wert:%d.%m.%Y}" if wert else "–"


def _person(p: Person) -> str:
    name = f"{p.vorname} {p.nachname}".strip()
    return f"{name} (geb. {_datum(p.geburtsdatum)})" if p.geburtsdatum else name


def _von(h: Haushalt, personen) -> dict:
    return {
        "status": h.get_status_display(),
        "kundengruppe": h.kundengruppe.name if h.kundengruppe else "",
        "ausweis": h.ausweis_gueltig_bis,
        "personen": sorted(_person(p) for p in personen),
    }


def schnappschuss(h: Haushalt | None) -> dict | None:
    """Vergleichbarer Stand eines Haushalts (frisch aus der Datenbank)."""
    if h is None:
        return None
    h = Haushalt.objects.select_related("kundengruppe").get(pk=h.pk)
    return _von(h, h.personen.all())


def schnappschuesse() -> dict[str, dict]:
    """Stand aller Haushalte nach Kundennummer (für den Import)."""
    haushalte = Haushalt.objects.select_related("kundengruppe").prefetch_related(
        Prefetch("personen", queryset=Person.objects.only("haushalt_id", "vorname", "nachname",
                                                          "geburtsdatum"))
    )  # fmt: skip
    return {h.kundennummer: _von(h, h.personen.all()) for h in haushalte}


def unterschiede(vorher: dict | None, nachher: dict | None) -> list[str]:
    """Lesbare Zeilen, was sich zwischen zwei Schnappschüssen geändert hat."""
    if vorher is None and nachher is None:
        return []
    if vorher is None:
        return ["Neu im Kundenstamm"]
    if nachher is None:
        return ["Nicht mehr im Kundenstamm"]
    zeilen = []
    if vorher["status"] != nachher["status"]:
        zeilen.append(f"Status: {vorher['status']} → {nachher['status']}")
    if vorher["kundengruppe"] != nachher["kundengruppe"]:
        zeilen.append(
            f"Kundengruppe: {vorher['kundengruppe'] or '–'} → {nachher['kundengruppe'] or '–'}"
        )
    alt, neu = vorher["ausweis"], nachher["ausweis"]
    if alt != neu:
        wort = "verlängert" if alt and neu and neu > alt else "gültig bis geändert"
        zeilen.append(f"Ausweis {wort}: {_datum(alt)} → {_datum(neu)}")
    alt_p, neu_p = set(vorher["personen"]), set(nachher["personen"])
    zeilen += [f"Person hinzugekommen: {p}" for p in sorted(neu_p - alt_p)]
    zeilen += [f"Person entfallen: {p}" for p in sorted(alt_p - neu_p)]
    return zeilen


def festhalten(kundennummer: str, vorher, nachher, *, quelle: str, von: str = "",
               zusatz: str = "") -> int:  # fmt: skip
    """Speichert die Unterschiede als Ereignisse; ``zusatz`` steht davor (z. B. „Aufgenommen“)."""
    zeilen = unterschiede(vorher, nachher)
    if zusatz:
        zeilen = [zusatz, *[z for z in zeilen if z != "Neu im Kundenstamm"]]
    HaushaltEreignis.objects.bulk_create(
        HaushaltEreignis(kundennummer=kundennummer, quelle=quelle, text=z[:300], von=von[:150])
        for z in zeilen
    )
    return len(zeilen)


def import_festhalten(vorher: dict[str, dict], nachher: dict[str, dict], von: str) -> int:
    """Alle Unterschiede eines Imports (vorher/nachher aus ``schnappschuesse()``)."""
    ereignisse = [
        HaushaltEreignis(kundennummer=nummer, quelle=HaushaltEreignis.Quelle.IMPORT, text=z[:300],
                         von=von[:150])
        for nummer in sorted(vorher.keys() | nachher.keys())
        for z in unterschiede(vorher.get(nummer), nachher.get(nummer))
    ]  # fmt: skip
    HaushaltEreignis.objects.bulk_create(ereignisse, batch_size=1000)
    return len(ereignisse)
