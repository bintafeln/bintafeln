from django.db import migrations

RECHT = "einlass.nachtragen"


def recht_geben(apps, schema_editor):
    """Abholungen von heute und gestern nachtragen für Büro und Ausgabe (ADR 0091)."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name__in=["Büro",
                                                                                    "Ausgabe"]):
        if RECHT not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, RECHT]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if RECHT in rolle.rechte:
            rolle.rechte = [c for c in rolle.rechte if c != RECHT]
            rolle.save()


class Migration(migrations.Migration):
    dependencies = [("konten", "0027_ansicht_stand")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
