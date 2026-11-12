import secrets

from django.db import migrations, models

import apps.aufruf.models


def schluessel_vergeben(apps, schema_editor):
    """Jede Ausgabestelle bekommt ihren eigenen, zufälligen Schlüssel für die Steuerungs-Links."""
    for e in apps.get_model("aufruf", "AufrufEinstellungen").objects.filter(steuer_schluessel=""):
        e.steuer_schluessel = secrets.token_urlsafe(24)
        e.save(update_fields=["steuer_schluessel"])


class Migration(migrations.Migration):
    dependencies = [("aufruf", "0012_aufrufeinstellungen_beenden_nach_minuten")]

    operations = [
        # Erst ohne „eindeutig“ anlegen, dann je Zeile füllen, dann eindeutig machen: Mit einer
        # Vorgabe bekämen sonst alle vorhandenen Zeilen denselben Wert.
        migrations.AddField(
            model_name="aufrufeinstellungen",
            name="steuer_schluessel",
            field=models.CharField(default="", editable=False, max_length=64),
            preserve_default=False,
        ),
        migrations.RunPython(schluessel_vergeben, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="aufrufeinstellungen",
            name="steuer_schluessel",
            field=models.CharField(
                default=apps.aufruf.models.neuer_schluessel,
                editable=False,
                help_text="Steckt in den Links der Steuerung am PC und am Handy, damit sie sich "
                "nicht erraten lassen. Die Steuerung braucht trotzdem Anmeldung und das Recht "
                "dazu.",
                max_length=64,
                unique=True,
                verbose_name="Schlüssel der Steuerungs-Links",
            ),
        ),
    ]
