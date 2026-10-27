from django.db import migrations

NAME = "Ehrenamtliche Helfer"


def anlegen(apps, schema_editor):
    """Helfer, die weder Mitglied noch Spender noch Kunde sind, gehören auch ins Adressbuch."""
    apps.get_model("adressen", "AdressKategorie").objects.get_or_create(
        name=NAME, defaults={"reihenfolge": 5}
    )


def loeschen(apps, schema_editor):
    apps.get_model("adressen", "AdressKategorie").objects.filter(
        name=NAME, adressen__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("adressen", "0002_kategorien")]

    operations = [migrations.RunPython(anlegen, loeschen)]
