from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

WOCHEN_JE_MONAT = Decimal(52) / Decimal(12)


def monatslohn_nachtragen(apps, schema_editor):
    """Für bestehende Verträge den Monatslohn aus Stundenlohn × Wochenstunden ableiten, damit die
    Anzeige wie bisher einen Monatslohn zeigt (bisher wurde er zur Laufzeit berechnet)."""
    Arbeitsvertrag = apps.get_model("personal", "Arbeitsvertrag")
    for v in Arbeitsvertrag.objects.filter(stundenlohn__isnull=False):
        if v.wochenstunden:
            v.monatslohn = (v.stundenlohn * v.wochenstunden * WOCHEN_JE_MONAT).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            v.save(update_fields=["monatslohn"])


def rueckwaerts(apps, schema_editor):
    """Nichts zu tun: das Feld wird mit RemoveField wieder entfernt."""


class Migration(migrations.Migration):
    dependencies = [("personal", "0004_anmerkung_einlass")]

    operations = [
        migrations.AddField(
            model_name="arbeitsvertrag",
            name="monatslohn",
            field=models.DecimalField(
                "Monatslohn (Euro brutto)",
                max_digits=8,
                decimal_places=2,
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(monatslohn_nachtragen, rueckwaerts),
    ]
