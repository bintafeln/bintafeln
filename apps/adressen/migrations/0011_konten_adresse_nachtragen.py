"""Konten ohne Adressbuch-Eintrag nachtragen.

Der bei der Einrichtung angelegte Admin (und jedes Konto, das außerhalb der Verwaltung entstanden
ist) bekam bisher keine verknüpfte Adresse. Dadurch fehlte er in den Adress- und Drucklisten, die
nur Personen im Adressbuch lesen. Diese Migration legt – wie 0007 – für jedes Konto außer dem einer
Ausgabestelle (Einlass-Tablet) eine Person-Adresse an, falls keine da ist, und markiert Konten mit
mindestens einer Rolle als „Ehrenamtliche Helfer“ (ADR 0097/0098). Idempotent, ändert sonst nichts.
"""

from django.db import migrations

HELFER = "Ehrenamtliche Helfer"


def konten_nachtragen(apps, schema_editor):
    Adresse = apps.get_model("adressen", "Adresse")
    AdressKategorie = apps.get_model("adressen", "AdressKategorie")
    Benutzer = apps.get_model("konten", "Benutzer")
    helfer, _ = AdressKategorie.objects.get_or_create(name=HELFER, defaults={"reihenfolge": 5})

    # Konten einer Ausgabestelle sind keine Personen (stelle_id gesetzt) → auslassen.
    for b in Benutzer.objects.filter(stelle__isnull=True):
        adr = Adresse.objects.filter(konto_id=b.pk).first()
        if adr is None:
            stamm = getattr(b, "stammdaten", None)
            adr = Adresse(
                art="person",
                vorname=(b.first_name or "")[:100],
                nachname=(b.last_name or b.username)[:100],
                email=b.email or "",
                konto_id=b.pk,
            )
            if stamm is not None:
                adr.anrede = stamm.anrede or ""
                adr.strasse = stamm.strasse or ""
                adr.plz = stamm.plz or ""
                adr.ort = stamm.ort or ""
                adr.telefon = stamm.telefon or ""
                adr.mobil = stamm.handy or ""
            adr.save()
        if b.groups.exists():
            adr.kategorien.add(helfer)


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0010_adresse_geburtsdatum"),
        ("konten", "0038_anmeldeeinstellungen_protokoll_tage_anmeldeprotokoll"),
    ]

    operations = [
        migrations.RunPython(konten_nachtragen, migrations.RunPython.noop),
    ]
