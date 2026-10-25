from django.db import migrations

NEU = ["adressen.sehen", "adressen.bearbeiten", "adressen.importieren"]


def recht_geben(apps, schema_editor):
    """Rechte für das Adressbuch (ADR 0044) für das Büro; Admin hat ohnehin alle."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        rolle.rechte = [*rolle.rechte, *(c for c in NEU if c not in rolle.rechte)]
        rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("adressen.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("konten", "0011_statistik_recht")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
