from django.db import migrations

HELFER = "Ehrenamtliche Helfer"  # Kategorie aus Migration 0003


def helfer_setzen(apps, schema_editor):
    """Wer in der Kategorie „Ehrenamtliche Helfer“ steht, bekommt das Kennzeichen helfer=True
    (ADR 0097). Die Kategorie bleibt erhalten; aktiv ist die Vorgabe."""
    Adresse = apps.get_model("adressen", "Adresse")
    Adresse.objects.filter(kategorien__name=HELFER).update(helfer=True)


def zuruecknehmen(apps, schema_editor):
    Adresse = apps.get_model("adressen", "Adresse")
    Adresse.objects.update(helfer=False)


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0004_adresse_helfer_adresse_helfer_aktiv_adresse_konto"),
    ]

    operations = [
        migrations.RunPython(helfer_setzen, zuruecknehmen),
    ]
