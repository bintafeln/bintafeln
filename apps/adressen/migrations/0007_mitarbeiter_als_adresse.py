"""Jedes Mitarbeiter-Konto wird eine Person im Adressbuch (ADR 0097).

Der Umbau hatte Adressen bisher nur für Fahrdienst- und Dienstplan-Teilnehmer angelegt.
Mitarbeitende mit Konto, aber ohne diese Einteilung (z. B. nur Rolle „Ausgabe“ oder im Büro,
Lager, in der Sortierung), fehlten deshalb im Adressbuch und waren nicht als Helfer markiert.
Diese Migration legt für jedes Konto – außer dem einer Ausgabestelle (Einlass-Tablet, ADR 0059) –
eine verknüpfte Adresse an, falls noch keine da ist, und markiert alle als ehrenamtliche Helfer
(Helfer sind überall tätig; einzelne Nicht-Helfer kann der Admin im Adressbuch abwählen).
"""

from django.db import migrations


def mitarbeiter_zu_adressen(apps, schema_editor):
    Adresse = apps.get_model("adressen", "Adresse")
    Benutzer = apps.get_model("konten", "Benutzer")

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
                helfer=True,
                helfer_aktiv=b.is_active,
            )
            if stamm is not None:
                adr.anrede = stamm.anrede or ""
                adr.strasse = stamm.strasse or ""
                adr.plz = stamm.plz or ""
                adr.ort = stamm.ort or ""
                adr.telefon = stamm.telefon or ""
                adr.mobil = stamm.handy or ""
            adr.save()
        elif not adr.helfer:  # vorhandene Adresse (z. B. aus dem Fahrdienst) als Helfer markieren
            adr.helfer = True
            adr.save(update_fields=["helfer"])


class Migration(migrations.Migration):
    dependencies = [
        ("adressen", "0006_adresse_fahrdienst"),
        ("konten", "0030_benutzer_listen_spalten_aus"),
    ]

    operations = [
        migrations.RunPython(mitarbeiter_zu_adressen, migrations.RunPython.noop),
    ]
