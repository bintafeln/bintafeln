from django.db import migrations

RECHTE = {
    "Büro": ("touren.stationen", "touren.stationen_bearbeiten"),
    "Fahrer": ("touren.stationen",),
    "Beifahrer": ("touren.stationen",),
}
ALLE = {"touren.stationen", "touren.stationen_bearbeiten"}


def rechte_geben(apps, schema_editor):
    """Touren (ADR 0147): Das Büro pflegt die Stationen, Fahrer und Beifahrer sehen sie und
    navigieren hin. Der Admin hat ohnehin alle Rechte."""
    Rolle = apps.get_model("konten", "Rolle")
    for name, codes in RECHTE.items():
        for rolle in Rolle.objects.filter(gruppe__name=name):
            neu = [c for c in codes if c not in rolle.rechte]
            if neu:
                rolle.rechte = [*rolle.rechte, *neu]
                rolle.save()


def rechte_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if ALLE & set(rolle.rechte):
            rolle.rechte = [c for c in rolle.rechte if c not in ALLE]
            rolle.save()


class Migration(migrations.Migration):
    dependencies = [("touren", "0001_initial"), ("konten", "0019_konto_der_ausgabestelle")]

    operations = [migrations.RunPython(rechte_geben, rechte_nehmen)]
