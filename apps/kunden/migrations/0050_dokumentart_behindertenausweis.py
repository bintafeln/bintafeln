from django.db import migrations


def anlegen(apps, schema_editor):
    """Dokumentart für das Foto des Behindertenausweises (ADR 0122); eine schon vorhandene
    bleibt, wie sie ist."""
    apps.get_model("kunden", "Dokumentart").objects.get_or_create(
        bezeichnung="Behindertenausweis", defaults={"aufbewahren_monate": 24}
    )


class Migration(migrations.Migration):
    dependencies = [
        ("kunden", "0049_verlegung_vorlauf"),
    ]

    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
