from django.db import migrations


def recht_geben(apps, schema_editor):
    """Nachrichten der Ausgabestellen zu Kunden (ADR 0062) liest das Büro."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        if "kunden.nachrichten" not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, "kunden.nachrichten"]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if c != "kunden.nachrichten"]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("konten", "0021_stellen_zwei_faktor")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
