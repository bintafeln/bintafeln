from django.db import migrations

HELFER = "Ehrenamtliche Helfer"  # Kategorie aus Migration 0003
EHEMALIGE = "Ehemalige Ehrenamtliche"


def anlegen(apps, schema_editor):
    """Legt die Kategorie „Ehemalige Ehrenamtliche“ an und kennzeichnet alle bestehenden
    Mitarbeiter-Adressen (Person mit Konto und mindestens einer Rolle) als „Ehrenamtliche Helfer“
    (ADR 0098). Beide Kategorien werden künftig in der Verwaltung automatisch gesetzt."""
    AdressKategorie = apps.get_model("adressen", "AdressKategorie")
    Adresse = apps.get_model("adressen", "Adresse")
    AdressKategorie.objects.get_or_create(name=EHEMALIGE, defaults={"reihenfolge": 6})
    helfer, _ = AdressKategorie.objects.get_or_create(name=HELFER, defaults={"reihenfolge": 5})
    mitarbeiter = (Adresse.objects
                   .filter(konto__isnull=False, konto__groups__isnull=False,
                           konto__stelle__isnull=True)
                   .distinct())  # fmt: skip
    for adresse in mitarbeiter:
        adresse.kategorien.add(helfer)


def zuruecknehmen(apps, schema_editor):
    """Nimmt nur die neu eingeführte Kategorie zurück, sofern sie niemandem mehr zugeordnet ist.
    Die „Ehrenamtliche Helfer“-Zuordnungen bleiben (welche vorher schon bestanden, lässt sich
    nicht mehr unterscheiden – sie schaden auch nicht)."""
    AdressKategorie = apps.get_model("adressen", "AdressKategorie")
    AdressKategorie.objects.filter(name=EHEMALIGE, adressen__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0008_felder_helfer_fahrdienst_entfernen"),
        ("konten", "0030_benutzer_listen_spalten_aus"),
    ]

    operations = [migrations.RunPython(anlegen, zuruecknehmen)]
