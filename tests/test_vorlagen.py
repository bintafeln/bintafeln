"""Alle Vorlagen: Kurz-Kommentare ``{# … #}`` gelten in Django nur innerhalb einer Zeile. Geht
einer über mehrere Zeilen, steht er als Text auf der Seite; dafür ``{% comment %}`` nehmen."""

from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


def test_kurz_kommentare_einzeilig():
    falsch = []
    for datei in [*WURZEL.glob("templates/**/*.html"), *WURZEL.glob("apps/*/templates/**/*.html")]:
        for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), start=1):
            if "{#" in zeile and "#}" not in zeile.split("{#", 1)[1]:
                falsch.append(f"{datei.relative_to(WURZEL)}:{nr}")
    assert not falsch, "Mehrzeiliger {# … #}-Kommentar: " + ", ".join(falsch)
