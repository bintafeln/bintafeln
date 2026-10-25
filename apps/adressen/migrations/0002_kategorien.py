from django.db import migrations

VORGABEN = ["Spender", "Lieferant/Markt", "Partner", "Presse", "Behörde"]


def anlegen(apps, schema_editor):
    kategorie = apps.get_model("adressen", "AdressKategorie")
    for nummer, name in enumerate(VORGABEN):
        kategorie.objects.get_or_create(name=name, defaults={"reihenfolge": nummer})


def loeschen(apps, schema_editor):
    apps.get_model("adressen", "AdressKategorie").objects.filter(
        name__in=VORGABEN, adressen__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("adressen", "0001_initial")]

    operations = [migrations.RunPython(anlegen, loeschen)]
