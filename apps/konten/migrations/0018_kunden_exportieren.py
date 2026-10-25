from django.db import migrations

RECHT = "kunden.exportieren"


def recht_geben(apps, schema_editor):
    """Kundenliste exportieren für Büro und Ausgabe."""
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
    dependencies = [("konten", "0017_ausgabetage")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
