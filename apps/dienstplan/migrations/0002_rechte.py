from django.db import migrations

VORGABEN = {
    "Büro": ["dienstplan.sehen", "dienstplan.planen"],
    "Ausgabe": ["dienstplan.sehen"],
}


def recht_geben(apps, schema_editor):
    """Dienstplan (ADR 0077): planen fürs Büro, sehen für die Ausgabe."""
    for name, rechte in VORGABEN.items():
        for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name=name):
            neu = [c for c in rechte if c not in rolle.rechte]
            if neu:
                rolle.rechte = [*rolle.rechte, *neu]
                rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("dienstplan.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("dienstplan", "0001_initial"), ("konten", "0024_wiedervorlage_null")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
