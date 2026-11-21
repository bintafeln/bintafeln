from django.db import migrations

WARENGRUPPEN = ["Obst/Gemüse", "Molkereiprodukte", "Fleisch/Wurst", "Backwaren", "Trockenware",
                "Süßigkeiten", "Sonstiges"]  # fmt: skip
RECHTE = {
    "Büro": ("touren.lieferschein", "touren.lieferscheine"),
    "Fahrer": ("touren.lieferschein",),
    "Beifahrer": ("touren.lieferschein",),
}
ALLE = {"touren.lieferschein", "touren.lieferscheine", "einstellungen.touren"}


def anlegen(apps, schema_editor):
    """Lieferscheine (ADR 0149): Warengruppen als Vorgabe (jede Tafel ändert sie in den
    Einstellungen) und die Rechte für Büro, Fahrer und Beifahrer. Einstellen darf der Admin."""
    Warengruppe = apps.get_model("touren", "Warengruppe")
    if not Warengruppe.objects.exists():
        for nr, name in enumerate(WARENGRUPPEN, start=1):
            Warengruppe.objects.create(name=name, reihenfolge=nr * 10)
    Rolle = apps.get_model("konten", "Rolle")
    for name, codes in RECHTE.items():
        for rolle in Rolle.objects.filter(gruppe__name=name):
            neu = [c for c in codes if c not in rolle.rechte]
            if neu:
                rolle.rechte = [*rolle.rechte, *neu]
                rolle.save()


def zurueck(apps, schema_editor):
    for rolle in apps.get_model("konten", "Rolle").objects.all():
        if ALLE & set(rolle.rechte):
            rolle.rechte = [c for c in rolle.rechte if c not in ALLE]
            rolle.save()


class Migration(migrations.Migration):
    dependencies = [("touren", "0005_lieferscheine")]

    operations = [migrations.RunPython(anlegen, zurueck)]
