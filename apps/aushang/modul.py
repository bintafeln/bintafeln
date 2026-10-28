"""Beschreibung des Moduls Aushang-Monitore für den Modulrahmen (ADR 0049, 0080). Ohne
Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Einstellungen/Dienstpläne", [
            ("aushang.einrichten", eintrag("Aushang-Monitore", "aushang:liste")),
        ]),
    ]  # fmt: skip


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
    kapitel=(("aushang", "Aushang-Monitore", ("aushang.einrichten",)),),
    menue=menue,
)  # fmt: skip
