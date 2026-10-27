from django.db import migrations

# Stand bei Erstellung (apps/core/auswahl.py FESTE_MERKMALE); Migrationen bleiben unverändert.
FESTE = [
    ("schwerbehindert", "Schwerbehindert", True, "rollstuhl"),
    ("vegetarier", "Vegetarier", False, ""),
    ("hilfe_einkauf", "Braucht Hilfe beim Einkauf", False, ""),
    ("taub", "Taub", True, ""),
    ("stumm", "Stumm", True, ""),
    ("blind", "Blind", True, ""),
]


def anlegen(apps, schema_editor):
    """Mitgelieferte Merkmale anlegen; ein schon vorhandenes Feld gleichen Schlüssels (z. B. aus
    dem Import) wird übernommen, nicht verdoppelt, und behält seine Einstellungen."""
    Zusatzfeld = apps.get_model("kunden", "Zusatzfeld")
    for i, (schluessel, bezeichnung, art9, ausweis) in enumerate(FESTE):
        feld = Zusatzfeld.objects.filter(schluessel=schluessel).first()
        if feld is None:
            Zusatzfeld.objects.create(
                schluessel=schluessel, bezeichnung=bezeichnung, gilt_fuer="person",
                typ="ja_nein", besondere_kategorie=art9, reihenfolge=100 + i, einlass=True,
                ausweis=ausweis,
            )  # fmt: skip
            continue
        if feld.typ == "ja_nein":
            feld.einlass = True
            feld.ausweis = feld.ausweis or ausweis
            feld.save()


def zuruecksetzen(apps, schema_editor):
    """Rückwärts nichts löschen: die Felder können schon Werte haben (die Spalten für Einlass und
    Ausweis entfernt die Migration davor)."""


class Migration(migrations.Migration):
    dependencies = [("kunden", "0028_zusatzfeld_einlass_ausweis")]

    operations = [migrations.RunPython(anlegen, zuruecksetzen)]
