from django.db import migrations

VORGABEN = {"Büro": ["listen.nutzen", "listen.teilen"], "Ausgabe": ["listen.nutzen"]}


def recht_geben(apps, schema_editor):
    """Listen (ADR 0063) für Büro und Ausgabe."""
    for name, rechte in VORGABEN.items():
        for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name=name):
            neu = [c for c in rechte if c not in rolle.rechte]
            if neu:
                rolle.rechte = [*rolle.rechte, *neu]
                rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("listen.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("listen", "0001_initial"), ("konten", "0022_recht_nachrichten")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
