"""Gemeinsame Personennummern-Reihe (ADR 0101): bereits vorhandenen, aktiven Mitarbeitenden, die
keine Vereinsmitglieder sind, eine Personalnummer aus derselben Reihe wie die Mitgliedsnummern
geben. Nichts wird gelöscht. Umkehrbar (die Nummern werden wieder entfernt)."""

from django.db import migrations


def _zaehler(MitgliederEinstellungen):
    e, _ = MitgliederEinstellungen.objects.get_or_create(pk=1)
    return e


def vergeben(apps, schema_editor):
    MitgliederEinstellungen = apps.get_model("mitglieder", "MitgliederEinstellungen")
    Mitglied = apps.get_model("mitglieder", "Mitglied")
    Stammdaten = apps.get_model("konten", "Stammdaten")
    Benutzer = apps.get_model("konten", "Benutzer")

    # Adressen, die Mitglied sind: deren Konten bekommen keine eigene Personalnummer (es gilt die
    # Mitgliedsnummer).
    mitglied_konten = set(
        Mitglied.objects.exclude(benutzer__isnull=True).values_list("benutzer_id", flat=True)
    )
    mitglied_adressen = set(Mitglied.objects.values_list("adresse_id", flat=True))

    belegte_mitglieds = {
        int(n) for n in Mitglied.objects.values_list("nummer", flat=True) if str(n).isdigit()
    }
    belegte_personal = {
        n for n in Stammdaten.objects.exclude(personalnummer__isnull=True)
        .values_list("personalnummer", flat=True)
    }  # fmt: skip
    belegt = belegte_mitglieds | belegte_personal

    e = _zaehler(MitgliederEinstellungen)
    naechste = e.naechste_nummer or 1

    konten = Benutzer.objects.filter(is_active=True, stelle__isnull=True).order_by(
        "last_name", "first_name", "username"
    )
    for b in konten:
        if b.pk in mitglied_konten:
            continue
        sd = Stammdaten.objects.filter(benutzer_id=b.pk).first()
        if sd is None or sd.personalnummer is not None:
            continue
        # Konten, deren Adressbuch-Eintrag Mitglied ist, auslassen (Mitgliedsnummer gilt)
        adresse = getattr(b, "adresse", None)
        if adresse is not None and adresse.pk in mitglied_adressen:
            continue
        while naechste in belegt:
            naechste += 1
        sd.personalnummer = naechste
        sd.save(update_fields=["personalnummer"])
        belegt.add(naechste)
        naechste += 1

    e.naechste_nummer = max(e.naechste_nummer or 1, naechste)
    e.save(update_fields=["naechste_nummer"])


def zuruecknehmen(apps, schema_editor):
    Stammdaten = apps.get_model("konten", "Stammdaten")
    Stammdaten.objects.update(personalnummer=None)


class Migration(migrations.Migration):
    dependencies = [
        ("mitglieder", "0003_namen_mehrzahl"),
        ("konten", "0033_stammdaten_personalnummer"),
        ("adressen", "0001_initial"),
    ]

    operations = [migrations.RunPython(vergeben, zuruecknehmen)]
