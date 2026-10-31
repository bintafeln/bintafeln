"""Dienstplan-Helfer werden Personen im Adressbuch (ADR 0097).

Für jeden ``Helfer`` entsteht (oder wird gefunden) eine ``Adresse`` mit Kennzeichen Helfer; die
festen Besetzungen, Ausfälle, Ersätze und Teamleitungen zeigen danach auf diese Adresse. Das alte
``Helfer``-Modell entfällt. Es wird nichts gelöscht – die Angaben wandern in das Adressbuch.
"""

from django.db import migrations, models
import django.db.models.deletion


def helfer_zu_adressen(apps, schema_editor):
    Helfer = apps.get_model("dienstplan", "Helfer")
    Adresse = apps.get_model("adressen", "Adresse")
    Besetzung = apps.get_model("dienstplan", "Besetzung")
    Ausfall = apps.get_model("dienstplan", "Ausfall")
    Ersatz = apps.get_model("dienstplan", "Ersatz")
    Diensttag = apps.get_model("dienstplan", "Diensttag")

    karte = {}  # helfer_pk -> adresse
    for h in Helfer.objects.all():
        adr = None
        if h.benutzer_id:
            adr = Adresse.objects.filter(konto_id=h.benutzer_id).first()
        if adr is not None:
            if not adr.helfer:
                adr.helfer = True
                adr.helfer_aktiv = h.aktiv
                adr.save(update_fields=["helfer", "helfer_aktiv"])
        else:
            if h.benutzer_id:
                b = h.benutzer
                vorname, nachname = b.first_name, (b.last_name or b.username)
                email = b.email or ""
            else:
                teile = (h.name or "").split()
                vorname = " ".join(teile[:-1]) if len(teile) > 1 else ""
                nachname = teile[-1] if teile else "Helfer"
                email = h.email or ""
            adr = Adresse.objects.create(
                art="person", vorname=vorname[:100], nachname=nachname[:100],
                telefon=h.telefon or "", email=email, notiz=h.anmerkung or "",
                helfer=True, helfer_aktiv=h.aktiv, konto_id=h.benutzer_id or None,
            )
        karte[h.pk] = adr

    for b in Besetzung.objects.all():
        b.person = karte.get(b.helfer_id)
        b.save(update_fields=["person"])
    for a in Ausfall.objects.all():
        a.person = karte.get(a.helfer_id)
        a.save(update_fields=["person"])
    for e in Ersatz.objects.all():
        e.person = karte.get(e.helfer_id)
        e.save(update_fields=["person"])
    for d in Diensttag.objects.exclude(teamleitung__isnull=True):
        d.teamleitung_neu = karte.get(d.teamleitung_id)
        d.save(update_fields=["teamleitung_neu"])

    # Die neuen Verweise (und die neu angelegten Adressen) sind Fremdschlüssel mit
    # aufgeschobener Prüfung. Solange diese Prüfung aussteht, scheitert der nächste
    # Schema-Schritt (DROP/RENAME einer Spalte) auf echten Daten an „pending trigger
    # events" auf adressen_adresse. Darum die Prüfungen hier sofort nachholen.
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [
        ("dienstplan", "0003_wieder_gesund"),
        ("adressen", "0005_helfer_aus_kategorie"),
    ]

    operations = [
        migrations.AddField(
            model_name="besetzung", name="person",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="dienst_besetzungen", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.AddField(
            model_name="ausfall", name="person",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="dienst_ausfaelle", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.AddField(
            model_name="ersatz", name="person",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="dienst_ersatz", to="adressen.adresse", verbose_name="Person"),
        ),
        migrations.AddField(
            model_name="diensttag", name="teamleitung_neu",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="adressen.adresse", verbose_name="Teamleitung",
                help_text="Bekommt Ausfälle dieses Tages per E-Mail. Leer = alle, die planen "
                "dürfen."),
        ),
        migrations.RunPython(helfer_zu_adressen, migrations.RunPython.noop),
        migrations.RemoveField(model_name="besetzung", name="helfer"),
        migrations.RemoveField(model_name="ausfall", name="helfer"),
        migrations.RemoveField(model_name="ersatz", name="helfer"),
        migrations.RemoveField(model_name="diensttag", name="teamleitung"),
        migrations.RenameField(model_name="besetzung", old_name="person", new_name="helfer"),
        migrations.RenameField(model_name="ausfall", old_name="person", new_name="helfer"),
        migrations.RenameField(model_name="ersatz", old_name="person", new_name="helfer"),
        migrations.RenameField(
            model_name="diensttag", old_name="teamleitung_neu", new_name="teamleitung"),
        # Kein ALTER … SET NOT NULL hier: das würde in derselben Transaktion nach der
        # Daten-Übernahme an „pending trigger events" auf adressen_adresse scheitern (nur auf
        # Servern mit echten Daten). Die Felder bleiben deshalb nullbar; gesetzt werden sie
        # ohnehin immer.
        migrations.DeleteModel(name="Helfer"),
    ]
