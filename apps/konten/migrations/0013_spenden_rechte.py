from django.db import migrations

NEU = ["spenden.sehen", "spenden.erfassen", "spenden.bestaetigen"]


def recht_geben(apps, schema_editor):
    """Rechte für Spenden (ADR 0045) für das Büro; Admin hat ohnehin alle."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        rolle.rechte = [*rolle.rechte, *(c for c in NEU if c not in rolle.rechte)]
        rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("spenden.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("konten", "0012_adressen_rechte")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
