from django.db import migrations


def recht_geben(apps, schema_editor):
    """Serienbriefe (ADR 0047) für das Büro; an Kunden nur mit eigenem Recht (Vorgabe Admin)."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        if "serienbriefe.erstellen" not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, "serienbriefe.erstellen"]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("serienbriefe.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("konten", "0014_mitglieder_rechte")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
