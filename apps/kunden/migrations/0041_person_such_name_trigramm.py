"""Suchname je Person + Trigramm-Index (pg_trgm) für den schnellen Kundenstamm-Abgleich.

Umkehrbar: Index, Feld und Erweiterung lassen sich wieder entfernen.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations, models

from apps.kunden import namen


def _fuellen(apps, schema_editor):
    Person = apps.get_model("kunden", "Person")
    zu_aendern = []
    for p in Person.objects.all().only("id", "vorname", "nachname", "such_name").iterator():
        wert = namen.such_name(p.vorname, p.nachname)
        if p.such_name != wert:
            p.such_name = wert
            zu_aendern.append(p)
        if len(zu_aendern) >= 1000:
            Person.objects.bulk_update(zu_aendern, ["such_name"])
            zu_aendern = []
    if zu_aendern:
        Person.objects.bulk_update(zu_aendern, ["such_name"])


def _leeren(apps, schema_editor):
    # Rückwärts nichts zu tun; das Feld wird ohnehin entfernt.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("kunden", "0040_ausgabestelle_dienstplan_sichtbar"),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddField(
            model_name="person",
            name="such_name",
            field=models.CharField(blank=True, default="", editable=False, max_length=201),
        ),
        migrations.RunPython(_fuellen, _leeren),
        migrations.AddIndex(
            model_name="person",
            index=GinIndex(
                name="kunden_person_such_trgm",
                fields=["such_name"],
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
