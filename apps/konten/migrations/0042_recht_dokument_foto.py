from django.db import migrations

RECHT = "kunden.dokument_foto"


def recht_geben(apps, schema_editor):
    """Foto eines Nachweises aufnehmen (ADR 0122): für alle Rollen, die Notizen schreiben dürfen
    (Einlass der Ausgabestellen, Büro); Admin hat ohnehin alle Rechte."""
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if "kunden.notizen" in rolle.rechte and RECHT not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, RECHT]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if RECHT in rolle.rechte:
            rolle.rechte = [c for c in rolle.rechte if c != RECHT]
            rolle.save()


class Migration(migrations.Migration):
    dependencies = [
        ("konten", "0041_anmeldesperre_einstellbar"),
    ]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
