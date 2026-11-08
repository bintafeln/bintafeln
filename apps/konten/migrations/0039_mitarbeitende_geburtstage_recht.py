from django.db import migrations

RECHT = "mitarbeitende.geburtstage"


def recht_geben(apps, schema_editor):
    """Geburtstage der Mitarbeitenden (Kalender + Startseite) für das Büro; Admin hat ohnehin
    alle Rechte."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        if RECHT not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, RECHT]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if RECHT in rolle.rechte:
            rolle.rechte = [c for c in rolle.rechte if c != RECHT]
            rolle.save()


class Migration(migrations.Migration):
    dependencies = [
        ("konten", "0038_anmeldeeinstellungen_protokoll_tage_anmeldeprotokoll"),
    ]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
