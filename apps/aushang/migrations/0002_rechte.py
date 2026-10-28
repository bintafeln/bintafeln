from django.db import migrations


def recht_geben(apps, schema_editor):
    """Aushang-Monitore (ADR 0080) einrichten darf das Büro, das auch die Dienstpläne plant."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        if "aushang.einrichten" not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, "aushang.einrichten"]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("aushang.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("aushang", "0001_initial"), ("konten", "0027_ansicht_stand")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
