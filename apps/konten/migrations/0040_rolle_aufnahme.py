from django.db import migrations

NAME = "Aufnahme"
RECHTE = [
    "antraege.sehen",
    "antraege.bearbeiten",
    "antraege.aufnehmen",
    "kunden.liste",
    "kunden.ansehen",
    "kunden.ausweis",
]


def rolle_anlegen(apps, schema_editor):
    """Mitgelieferte Rolle „Aufnahme“ für Neuaufnahmen anlegen (Anträge in den Kundenstamm
    übernehmen). Bestehende Installationen bekommen sie damit ohne erneute Einrichtung; ist sie
    schon da (z. B. gleicher Name von Hand angelegt), bleiben ihre Rechte unangetastet."""
    Group = apps.get_model("auth", "Group")
    Rolle = apps.get_model("konten", "Rolle")
    gruppe, _ = Group.objects.get_or_create(name=NAME)
    Rolle.objects.get_or_create(
        gruppe=gruppe,
        defaults={
            "rechte": list(RECHTE),
            "reihenfolge": 15,
            "zwei_faktor_pflicht": True,
            "braucht_belehrung": False,
            "braucht_fuehrerschein": False,
        },
    )


def rolle_entfernen(apps, schema_editor):
    """Nur die unveränderte, von dieser Migration angelegte Rolle wieder entfernen – eine von Hand
    angepasste gleichen Namens bleibt."""
    Group = apps.get_model("auth", "Group")
    Rolle = apps.get_model("konten", "Rolle")
    gruppe = Group.objects.filter(name=NAME).first()
    if not gruppe:
        return
    rolle = Rolle.objects.filter(gruppe=gruppe).first()
    if rolle and set(rolle.rechte) == set(RECHTE) and not gruppe.user_set.exists():
        gruppe.delete()  # löscht die Rolle (OneToOne, CASCADE) mit


class Migration(migrations.Migration):
    dependencies = [
        ("konten", "0039_mitarbeitende_geburtstage_recht"),
    ]

    operations = [migrations.RunPython(rolle_anlegen, rolle_entfernen)]
