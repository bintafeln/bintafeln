"""Falsche Bar-Buchungen aus importierten Beiträgen entfernen.

Migration 0013 und der Import haben für Abholungen aus der Tagesliste des bisherigen Programms den
Beitrag als Bareinnahme gebucht. Der Beitrag ist aber nur der fällige Betrag: Wer im Voraus bezahlt
hatte, zahlte an dem Tag nichts. Diese Buchungen (Anmerkung „Beitrag laut Import“, Soll = Haben,
ohne Wirkung auf den Kontostand) werden entfernt. Wird die Tagesliste erneut über „Kundenstamm
importieren → ergänzen“ eingespielt, bucht bintafeln das wirklich Gezahlte aus dem Kontostand.
Rückwärts entstehen die Buchungen wie in 0013 wieder.
"""

from importlib import import_module

from django.db import migrations

ALT = import_module("apps.ausgabe.migrations.0013_beitraege_aus_import_nachtragen")


def entfernen(apps, schema_editor):
    ALT.entfernen(apps, schema_editor)


def wiederherstellen(apps, schema_editor):
    ALT.nachtragen(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [("ausgabe", "0013_beitraege_aus_import_nachtragen")]

    operations = [migrations.RunPython(entfernen, wiederherstellen)]
