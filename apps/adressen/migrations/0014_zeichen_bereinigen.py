from django.db import migrations

from apps.core import zeichen

FELDER = ("organisation", "vorname", "nachname", "ansprechperson", "strasse", "plz", "ort", "land")


def bereinigen(apps, schema_editor):
    """Ligaturen („ff“ als ein Zeichen) und unsichtbare Zeichen aus vorhandenen Adressen
    entfernen: Sie kamen aus Importen und ausgelesenen PDFs und erschienen im Druck als
    schwarzer Block. Am sichtbaren Text ändert sich nichts."""
    Adresse = apps.get_model("adressen", "Adresse")
    for adresse in Adresse.objects.only("pk", *FELDER).iterator():
        neu = {f: zeichen.bereinigen(getattr(adresse, f)) for f in FELDER}
        geaendert = {f: w for f, w in neu.items() if w != getattr(adresse, f)}
        if geaendert:
            Adresse.objects.filter(pk=adresse.pk).update(**geaendert)


class Migration(migrations.Migration):
    dependencies = [("adressen", "0013_kategorie_verstorben")]

    operations = [migrations.RunPython(bereinigen, migrations.RunPython.noop)]
