from django.db import migrations

VORGABEN = {
    "Ausgabe": ["abrechnung.fuehren"],
    "Büro": ["abrechnung.fuehren", "abrechnung.pruefen"],
}


def recht_geben(apps, schema_editor):
    """Abrechnung (ADR 0060): Ausgabe führt sie für die eigene Ausgabestelle, das Büro prüft."""
    for name, rechte in VORGABEN.items():
        for rolle in apps.get_model("konten", "Rolle").objects.filter(gruppe__name=name):
            neu = [c for c in rechte if c not in rolle.rechte]
            if neu:
                rolle.rechte = [*rolle.rechte, *neu]
                rolle.save()


def recht_nehmen(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        rolle.rechte = [c for c in rolle.rechte if not c.startswith("abrechnung.")]
        rolle.save()


class Migration(migrations.Migration):
    dependencies = [("abrechnung", "0001_initial"), ("konten", "0019_konto_der_ausgabestelle")]

    operations = [migrations.RunPython(recht_geben, recht_nehmen)]
