"""Vorgeschlagene Zusatzfelder für den Haushalt (ausgeschaltet; die Tafel schaltet sie ein)."""

from django.db import migrations

VORSCHLAEGE = [
    # schluessel, bezeichnung, typ, optionen, besondere Kategorie (Art. 9 DSGVO)
    ("ernaehrung", "Ernährung", "auswahl", "vegetarisch\nvegan", False),
    ("kein_schweinefleisch", "Kein Schweinefleisch", "ja_nein", "", True),
    ("allergien", "Allergien / Unverträglichkeiten", "text", "", True),
    ("haustiere", "Haustiere (Tierfutter)", "ja_nein", "", False),
    ("keine_kochmoeglichkeit", "Keine Kochmöglichkeit", "ja_nein", "", False),
]


def anlegen(apps, schema_editor):
    Zusatzfeld = apps.get_model("kunden", "Zusatzfeld")
    for i, (schluessel, bezeichnung, typ, optionen, art9) in enumerate(VORSCHLAEGE):
        Zusatzfeld.objects.get_or_create(
            schluessel=schluessel,
            defaults={"bezeichnung": bezeichnung, "gilt_fuer": "haushalt", "typ": typ,
                      "optionen": optionen, "besondere_kategorie": art9,
                      "reihenfolge": 100 + i, "aktiv": False},
        )  # fmt: skip


def entfernen(apps, schema_editor):
    """Nur die unveränderten, nie benutzten Vorschläge wieder entfernen."""
    Zusatzfeld = apps.get_model("kunden", "Zusatzfeld")
    Haushalt = apps.get_model("kunden", "Haushalt")
    for schluessel, bezeichnung, *_ in VORSCHLAEGE:
        if not Haushalt.objects.filter(zusatz__has_key=schluessel).exists():
            Zusatzfeld.objects.filter(schluessel=schluessel, bezeichnung=bezeichnung,
                                      aktiv=False).delete()  # fmt: skip


class Migration(migrations.Migration):
    dependencies = [("kunden", "0016_rechte_in_rollen")]

    operations = [migrations.RunPython(anlegen, entfernen)]
