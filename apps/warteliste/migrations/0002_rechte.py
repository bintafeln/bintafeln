from django.db import migrations

RECHTE = ["warteliste.sehen", "warteliste.bearbeiten"]


def recht_geben(apps, schema_editor):
    """Warteliste (ADR 0051) für das Büro; einstellen nur Admin (Vorgabe)."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        neu = [c for c in RECHTE if c not in rolle.rechte]
        if neu:
            rolle.rechte = [*rolle.rechte, *neu]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("warteliste.")
                        and c != "einstellungen.warteliste"]  # fmt: skip
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("warteliste", "0001_initial"), ("konten", "0015_serienbriefe_rechte")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
