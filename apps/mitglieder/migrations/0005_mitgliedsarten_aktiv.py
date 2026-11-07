"""Nur noch zwei Mitgliedsarten: „Aktives Mitglied“ und „Nicht aktives Mitglied“ (ADR-Notiz: die
Tafel kennt keine ordentlichen/Förder-Mitglieder, sondern unterscheidet nur aktiv von nicht aktiv).
Bestehende Werte werden einmalig sinngemäß umgestellt; passive/fördernde Arten gelten als nicht
aktiv, alle übrigen als aktiv. Nichts wird gelöscht. Umkehrbar (no-op: die neuen Werte bleiben)."""

from django.db import migrations

NICHT_AKTIV = {"Passives Mitglied", "Fördermitglied", "Nicht aktives Mitglied"}


def umstellen(apps, schema_editor):
    Mitglied = apps.get_model("mitglieder", "Mitglied")
    for art in Mitglied.objects.values_list("art", flat=True).distinct():
        if art in ("Aktives Mitglied", "Nicht aktives Mitglied"):
            continue
        neu = "Nicht aktives Mitglied" if art in NICHT_AKTIV else "Aktives Mitglied"
        Mitglied.objects.filter(art=art).update(art=neu)


class Migration(migrations.Migration):
    dependencies = [("mitglieder", "0004_personalnummern_bestehende")]

    operations = [migrations.RunPython(umstellen, migrations.RunPython.noop)]
