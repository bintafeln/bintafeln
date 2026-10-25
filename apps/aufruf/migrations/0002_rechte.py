from django.db import migrations

RECHT = "aufruf.steuern"


def recht_geben(apps, schema_editor):
    """Aufruf steuern (ADR 0050) für Büro und Ausgabe; einstellen nur Admin (Vorgabe)."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name__in=["Büro", "Ausgabe"]):
        if RECHT not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, RECHT]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("aufruf.")
                        and c != "einstellungen.aufruf"]  # fmt: skip
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("aufruf", "0001_initial"), ("konten", "0015_serienbriefe_rechte")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
