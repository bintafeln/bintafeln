"""Falsch als „Organisation" gespeicherte Personen heilen.

Mitarbeitende sind Personen im Adressbuch (ADR 0097). Durch frühere Umbauten konnte ein Konto an
eine vorhandene „Organisation"-Adresse gehängt worden sein, ohne die Art zu korrigieren; 0007/0011
legen nur **fehlende** Adressen an und fassen vorhandene nicht an. Solche Einträge erscheinen im
Adressbuch (das alle Arten zeigt), fehlen aber in den reinen Personen-Listen – „Liste
zusammenstellen" blieb dadurch leer.

Diese Migration setzt die Art auf „Person“, wo sie es sein muss: bei jeder Adresse mit Konto und
bei jeder „Organisation" ohne Organisationsnamen, aber mit Nachnamen. Fehlende Konto-Adressen
werden – wie 0011 – nachgetragen. Idempotent, löscht nichts.
"""

from django.db import migrations


def heilen(apps, schema_editor):
    Adresse = apps.get_model("adressen", "Adresse")
    Benutzer = apps.get_model("konten", "Benutzer")

    # 1) Konten ohne Adresse nachtragen (wie 0011, falls welche fehlen) – als Person.
    for b in Benutzer.objects.filter(stelle__isnull=True):
        if Adresse.objects.filter(konto_id=b.pk).exists():
            continue
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

    # 2) Falsch als „Organisation" gespeicherte Personen heilen.
    Adresse.objects.filter(konto__isnull=False).exclude(art="person").update(art="person")
    Adresse.objects.filter(art="organisation", organisation="").exclude(nachname="").update(
        art="person"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0011_konten_adresse_nachtragen"),
    ]

    operations = [
        migrations.RunPython(heilen, migrations.RunPython.noop),
    ]
