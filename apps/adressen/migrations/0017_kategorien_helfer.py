"""Kategorien „Ehrenamtliche Helfer“ → „Helfer“, „Ehemalige Ehrenamtliche“ → „Ehemalige Helfer“.

Die Kategorie bekommt jede Person mit Konto und Rolle – auch fest Angestellte. „Ehrenamtliche
Helfer“ behauptete damit etwas, das nicht stimmt; ob jemand ehrenamtlich oder angestellt ist, sagt
das Feld „Beschäftigung“ am Konto. Die Zuordnungen bleiben alle erhalten. Gibt es die neue
Kategorie schon (von der Tafel selbst angelegt), werden beide zusammengeführt. Rückwärts werden
die Namen zurückgesetzt (eine Zusammenführung bleibt).
"""

from django.db import migrations

NAMEN = [("Ehrenamtliche Helfer", "Helfer"), ("Ehemalige Ehrenamtliche", "Ehemalige Helfer")]


def _umbenennen(apps, paare):
    AdressKategorie = apps.get_model("adressen", "AdressKategorie")
    for alt, neu in paare:
        alte = AdressKategorie.objects.filter(name=alt).first()
        if alte is None:
            continue
        neue = AdressKategorie.objects.filter(name=neu).first()
        if neue is None:
            alte.name = neu
            alte.save(update_fields=["name"])
            continue
        for adresse in alte.adressen.all():
            adresse.kategorien.add(neue)
        alte.delete()


def vorwaerts(apps, schema_editor):
    _umbenennen(apps, NAMEN)


def rueckwaerts(apps, schema_editor):
    _umbenennen(apps, [(neu, alt) for alt, neu in NAMEN])


class Migration(migrations.Migration):
    dependencies = [("adressen", "0016_email_konto_adresse")]

    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]
