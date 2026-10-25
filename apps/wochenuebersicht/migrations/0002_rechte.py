from django.db import migrations

RECHTE = ["wochenuebersicht.sehen", "wochenuebersicht.bearbeiten"]


def recht_geben(apps, schema_editor):
    """Wochenübersicht (ADR 0054) für das Büro."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        neu = [c for c in RECHTE if c not in rolle.rechte]
        if neu:
            rolle.rechte = [*rolle.rechte, *neu]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("wochenuebersicht.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("wochenuebersicht", "0001_initial"), ("konten", "0016_vertraute_geraete")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
