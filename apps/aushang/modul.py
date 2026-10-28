"""Beschreibung des Moduls Aushang-Monitore für den Modulrahmen (ADR 0049, 0080). Ohne
Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    pin = eintrag("Meine PIN für Monitore", "aushang:meine_pin")
    return [
        ("Dienstpläne", [("dienstplan.sehen", pin), ("fahrdienst.sehen", pin)]),
        ("Einstellungen/Dienstpläne", [
            ("aushang.einrichten", eintrag("Aushang-Monitore", "aushang:liste")),
        ]),
    ]  # fmt: skip


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.aushang.models import MonitorPin

    eintrag = MonitorPin.objects.filter(benutzer=benutzer).first()
    if eintrag:
        pdf.ueberschrift("Aushang-Monitore")
        pdf.absatz(f"PIN für das Ändern am Monitor eingerichtet, zuletzt geändert am "
                   f"{eintrag.geaendert_am:%d.%m.%Y}. Gespeichert ist nur ein Prüfwert, nicht "
                   "die PIN selbst.")  # fmt: skip


MODUL = Modul(
    kennung="aushang",
    titel="Aushang-Monitore",
    beschreibung="Dienstplan und Fahrerplan ganzseitig auf einem Monitor, ohne Anmeldung, "
    "mehrere Seiten im Wechsel oder nebeneinander",
    app_label="aushang",
    pfade=("/aushang/",),
    rechte=(
        ("aushang.einrichten", "Aushang-Monitore einrichten",
         "Seiten eines Plans nur mit dem Recht, ihn zu planen."),
    ),
    vorgaben={"Büro": ("aushang.einrichten",)},
    kapitel=(
        ("aushang", "Aushang-Monitore",
         ("aushang.einrichten", "dienstplan.sehen", "fahrdienst.sehen")),
    ),
    menue=menue,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
)  # fmt: skip
