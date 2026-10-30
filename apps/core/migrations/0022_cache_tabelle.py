"""Tabelle für den Datenbank-Cache (ADR 0093): gemeinsam über alle Prozesse, übersteht Updates.

Sie trägt u. a. die Zähler der Sperre nach zu vielen Anmeldeversuchen. ``createcachetable`` legt
sie nach dem Schema von Djangos DatabaseCache an und überspringt sie, wenn sie schon da ist.
"""

from django.core.management import call_command
from django.db import migrations

TABELLE = "bintafeln_cache"


def anlegen(apps, schema_editor):
    call_command("createcachetable", TABELLE, database=schema_editor.connection.alias, verbosity=0)


def entfernen(apps, schema_editor):
    schema_editor.execute(f'DROP TABLE IF EXISTS "{TABELLE}"')


class Migration(migrations.Migration):
    dependencies = [("core", "0021_verzeichnis")]

    operations = [migrations.RunPython(anlegen, entfernen)]
