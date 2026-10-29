from django.db import migrations


def recht_geben(apps, schema_editor):
    """Tickets (ADR 0087): Das Büro sieht und bearbeitet alle Tickets."""
    for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name="Büro"):
        if "tickets.bearbeiten" not in rolle.rechte:
            rolle.rechte = [*rolle.rechte, "tickets.bearbeiten"]
            rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("tickets.")
                        and c != "einstellungen.tickets"]  # fmt: skip
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("tickets", "0001_initial"), ("konten", "0027_ansicht_stand")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
