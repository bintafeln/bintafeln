"""E-Mail von Adresse und Konto angleichen.

Adresse und Anmelde-Konto einer Person führten die E-Mail bisher getrennt. Stand sie nur in der
Adresse, fehlte sie in den Team-Listen, und Einladung oder Passwort-Link ließen sich nicht
schicken. Diese Migration füllt nur die jeweils leere Seite; weichen beide voneinander ab, bleibt
alles, wie es ist. Rückwärts geschieht nichts (die ergänzten Angaben schaden nicht).
"""

from django.db import migrations


def angleichen(apps, schema_editor):
    Adresse = apps.get_model("adressen", "Adresse")
    Benutzer = apps.get_model("konten", "Benutzer")
    for adresse in Adresse.objects.filter(konto__isnull=False, konto__stelle__isnull=True):
        konto = Benutzer.objects.get(pk=adresse.konto_id)
        if adresse.email and not konto.email:
            Benutzer.objects.filter(pk=konto.pk).update(email=adresse.email)
        elif konto.email and not adresse.email:
            Adresse.objects.filter(pk=adresse.pk).update(email=konto.email)


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0015_adressnummer"),
        ("konten", "0044_listen_filter"),
    ]

    operations = [migrations.RunPython(angleichen, migrations.RunPython.noop)]
