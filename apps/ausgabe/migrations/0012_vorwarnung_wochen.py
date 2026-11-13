"""Vorwarnung vor Ablauf des Ausweises in Wochen statt Tagen; Vorgabe 5 Wochen.

Nie geänderte 14 Tage (die alte Vorgabe) werden zu 5 Wochen, eigene Werte auf volle Wochen
aufgerundet (7 Tage → 1 Woche, 10 Tage → 2 Wochen). Rückwärts: Wochen × 7 Tage.
"""

from django.core.validators import MaxValueValidator
from django.db import migrations, models

ALTE_VORGABE_TAGE, NEUE_VORGABE_WOCHEN = 14, 5


def in_wochen(apps, schema_editor):
    for e in apps.get_model("ausgabe", "AusgabeEinstellungen").objects.all():
        tage = e.vorwarnung_tage
        e.vorwarnung_wochen = NEUE_VORGABE_WOCHEN if tage == ALTE_VORGABE_TAGE else -(-tage // 7)
        e.save(update_fields=["vorwarnung_wochen"])


def in_tage(apps, schema_editor):
    for e in apps.get_model("ausgabe", "AusgabeEinstellungen").objects.all():
        e.vorwarnung_tage = min(e.vorwarnung_wochen * 7, 365)
        e.save(update_fields=["vorwarnung_tage"])


class Migration(migrations.Migration):
    dependencies = [("ausgabe", "0011_buchung_importiert")]

    operations = [
        migrations.AddField(
            model_name="ausgabeeinstellungen",
            name="vorwarnung_wochen",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="So viele Wochen vor Ablauf des Ausweises zeigt die Ampel gelb. "
                "0 = keine Vorwarnung.",
                validators=[MaxValueValidator(52)],
                verbose_name="Vorwarnung vor Ablauf des Ausweises (Wochen)",
            ),
        ),
        migrations.RunPython(in_wochen, in_tage),
        migrations.RemoveField(model_name="ausgabeeinstellungen", name="vorwarnung_tage"),
    ]
