"""Alle Adressen mit einer Spende (ohne reine Mitgliedsbeiträge) bekommen die Kategorie „Spender“
(ADR 0132). Fügt nur hinzu, löscht nichts."""

from django.db import migrations

SPENDER = "Spender"


def markieren(apps, schema_editor):
    kategorie_modell = apps.get_model("adressen", "AdressKategorie")
    adresse = apps.get_model("adressen", "Adresse")
    kategorie, _ = kategorie_modell.objects.get_or_create(name=SPENDER)
    if not kategorie.aktiv:
        return
    ids = adresse.objects.filter(spenden__mitgliedsbeitrag=False).values_list("pk", flat=True)
    kategorie.adressen.add(*set(ids))


class Migration(migrations.Migration):
    dependencies = [("spenden", "0006_unterschrift"), ("adressen", "0002_kategorien")]

    # Rückwärts nichts zu tun: Die Kategorie bleibt an den Adressen, entfernt wird nichts.
    operations = [migrations.RunPython(markieren, migrations.RunPython.noop)]
