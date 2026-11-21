from django.db import migrations

RECHTE = {
    "Büro": ("touren.fahren", "touren.planen"),
    "Fahrer": ("touren.fahren",),
    "Beifahrer": ("touren.fahren",),
}
ALLE = {"touren.fahren", "touren.planen"}


def rechte_geben(apps, schema_editor):
    """Touren (ADR 0148): Das Büro plant, Fahrer und Beifahrer sehen und fahren die Touren."""
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
    dependencies = [("touren", "0003_touren")]

    operations = [migrations.RunPython(rechte_geben, rechte_nehmen)]
