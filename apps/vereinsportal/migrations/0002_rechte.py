from django.db import migrations

RECHT = "vereinsportal.nutzen"


def recht_geben(apps, schema_editor):
    """Spendenbelege aus dem Vereinsportal (ADR 0126): das Büro darf einlesen und auswerten."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        if RECHT not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, RECHT]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if RECHT in rolle.rechte:
            rolle.rechte = [c for c in rolle.rechte if c != RECHT]
            rolle.save()


class Migration(migrations.Migration):
    dependencies = [("vereinsportal", "0001_initial"), ("konten", "0019_konto_der_ausgabestelle")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
