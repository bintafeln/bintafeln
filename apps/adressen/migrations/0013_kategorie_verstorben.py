from django.db import migrations

NAME = "Verstorben"


def anlegen(apps, schema_editor):
    """Mitgelieferte Adress-Kategorie „Verstorben" anlegen (zum Markieren und Filtern); bestehende
    Installationen bekommen sie damit ohne eigenes Zutun. Ist sie schon da, bleibt sie unverändert."""
    Kategorie = apps.get_model("adressen", "AdressKategorie")
    Kategorie.objects.get_or_create(name=NAME, defaults={"reihenfolge": 7})


def entfernen(apps, schema_editor):
    """Nur die leere, von dieser Migration angelegte Kategorie wieder entfernen – eine, der schon
    Adressen zugeordnet sind, bleibt."""
    Kategorie = apps.get_model("adressen", "AdressKategorie")
    kategorie = Kategorie.objects.filter(name=NAME).first()
    if kategorie and not kategorie.adressen.exists():
        kategorie.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0012_personen_art_heilen"),
    ]

    operations = [migrations.RunPython(anlegen, entfernen)]
