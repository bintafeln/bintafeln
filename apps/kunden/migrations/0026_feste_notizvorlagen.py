from django.db import migrations

# Stand bei Erstellung (apps/core/auswahl.py FESTE_ANLIEGEN); Migrationen bleiben unverändert.
FESTE = {
    "verlaengern": "Bescheide geprüft – bitte Ausweis verlängern",
    "ausweis": "Neuen Ausweis drucken",
}


def anlegen(apps, schema_editor):
    """Feste Notiz-Vorlagen anlegen, falls die Tafel noch keine mit diesem Anliegen hat."""
    NotizVorlage = apps.get_model("kunden", "NotizVorlage")
    for melden, text in FESTE.items():
        if not NotizVorlage.objects.filter(melden=melden).exists():
            NotizVorlage.objects.create(text=text, melden=melden, reihenfolge=90)


class Migration(migrations.Migration):
    dependencies = [("kunden", "0025_notiz_an_ausgabestelle")]

    # Rückwärts nichts löschen: die Vorlagen können schon benutzt worden sein
    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
