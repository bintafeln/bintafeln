"""Fahrdienst: eingeteilt werden Personen aus dem Adressbuch statt Konten (ADR 0097).

Für jedes bisher im Fahrdienst genutzte Konto entsteht (oder wird gefunden) eine ``Adresse`` mit
Fahrdienst-Kennzeichen: „Fahrer“, wenn das Konto die Rolle Fahrer hat, sonst „nur Beifahrer“.
Feste Besetzung, Springer, Ausfälle und Ersätze zeigen danach auf die Person. Es wird nichts
gelöscht; die Benachrichtigungs-Empfänger (Planende) bleiben Konten.
"""

import django.db.models.deletion
from django.db import migrations, models


def benutzer_zu_adressen(apps, schema_editor):
    Adresse = apps.get_model("adressen", "Adresse")
    Benutzer = apps.get_model("konten", "Benutzer")
    Besetzung = apps.get_model("fahrdienst", "Besetzung")
    Springer = apps.get_model("fahrdienst", "Springer")
    Ausfall = apps.get_model("fahrdienst", "Ausfall")
    Ersatz = apps.get_model("fahrdienst", "Ersatz")

    fahrer_ids = set(
        Benutzer.objects.filter(groups__name="Fahrer").values_list("pk", flat=True)
    )
    karte = {}

    def person_fuer(benutzer_id):
        if benutzer_id is None:
            return None
        if benutzer_id in karte:
            return karte[benutzer_id]
        rolle = "fahrer" if benutzer_id in fahrer_ids else "beifahrer"
        adr = Adresse.objects.filter(konto_id=benutzer_id).first()
        if adr is None:
            b = Benutzer.objects.get(pk=benutzer_id)
            adr = Adresse.objects.create(
                art="person", vorname=(b.first_name or "")[:100],
                nachname=(b.last_name or b.username)[:100], email=b.email or "",
                konto_id=benutzer_id, helfer_aktiv=True, fahrdienst=rolle,
            )
        elif not adr.fahrdienst:
            adr.fahrdienst = rolle
            adr.save(update_fields=["fahrdienst"])
        karte[benutzer_id] = adr
        return adr

    for b in Besetzung.objects.all():
        b.person = person_fuer(b.benutzer_id)
        b.save(update_fields=["person"])
    for s in Springer.objects.all():
        s.person = person_fuer(s.benutzer_id)
        s.save(update_fields=["person"])
    for a in Ausfall.objects.all():
        a.person = person_fuer(a.benutzer_id)
        a.save(update_fields=["person"])
    for e in Ersatz.objects.all():
        e.person = person_fuer(e.benutzer_id)
        e.save(update_fields=["person"])

    # Siehe dienstplan.0004: aufgeschobene Fremdschlüssel-Prüfungen jetzt nachholen, sonst
    # scheitert der nächste Schema-Schritt auf echten Daten an „pending trigger events".
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [
        ("fahrdienst", "0006_wieder_gesund"),
        ("adressen", "0006_adresse_fahrdienst"),
    ]

    operations = [
        migrations.AddField(
            model_name="besetzung", name="person",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="fahr_besetzungen", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.AddField(
            model_name="springer", name="person",
            field=models.OneToOneField(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="fahr_springer", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.AddField(
            model_name="ausfall", name="person",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="fahr_ausfaelle", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.AddField(
            model_name="ersatz", name="person",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="fahr_ersatz", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.RunPython(benutzer_zu_adressen, migrations.RunPython.noop),
        migrations.RemoveField(model_name="besetzung", name="benutzer"),
        migrations.RemoveField(model_name="springer", name="benutzer"),
        migrations.RemoveField(model_name="ausfall", name="benutzer"),
        migrations.RemoveField(model_name="ersatz", name="benutzer"),
        # Kein ALTER … SET NOT NULL hier (siehe dienstplan.0004): das würde auf Servern mit
        # echten Daten an „pending trigger events" auf adressen_adresse scheitern. Die Felder
        # bleiben nullbar; gesetzt werden sie ohnehin immer.
    ]
