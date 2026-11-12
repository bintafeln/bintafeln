"""Die schon eingelesenen Belege aus dem Vereinsportal kommen in den Spendenpool (ADR 0128).

Je Beleg: der Spender im Adressbuch (vorhandene Adresse mit gleichem Namen und gleicher PLZ,
sonst neu), eine Spende mit Datum, Betrag und Belegnummer und das PDF als Spendenbeleg daran.
Die verschlüsselte Datei wird in den Ordner der Spendenbelege verschoben, nicht kopiert und nicht
gelöscht. Erst die nächste Migration entfernt die dann leere eigene Tabelle.
"""

import datetime as dt
import io

from django.db import migrations
from django.utils import timezone

ALT, NEU = "vereinsportal", "spendenbelege"
VON = "Update (Vereinsportal)"


def _datum_aus_datei(beleg):
    """Belege aus der Zeit vor dem Spendendatum: den Tag der Zuwendung aus dem PDF lesen."""
    from pypdf import PdfReader

    from apps.core import privatdateien
    from apps.vereinsportal import einlesen

    try:
        inhalt = privatdateien.lesen(ALT, beleg.datei)
        seiten = PdfReader(io.BytesIO(inhalt)).pages
        zeilen = [z.strip() for s in seiten for z in (s.extract_text() or "").split("\n")]
        return einlesen.spendendatum([z for z in zeilen if z])
    except Exception:  # noqa: BLE001 – nicht lesbar: der Ersatzwert unten gilt
        return None


def _datei_verschieben(name):
    from apps.core import privatdateien

    quelle, ziel = privatdateien.pfad(ALT, name), privatdateien.pfad(NEU, name)
    if quelle.exists() and not ziel.exists():
        ziel.parent.mkdir(parents=True, exist_ok=True)
        quelle.rename(ziel)


def in_den_pool(apps, schema_editor):
    from apps.vereinsportal import namen

    Beleg = apps.get_model("vereinsportal", "Beleg")
    Kontakt = apps.get_model("vereinsportal", "Kontakt")
    Adresse = apps.get_model("adressen", "Adresse")
    Spende = apps.get_model("spenden", "Spende")
    SpendenBeleg = apps.get_model("spenden", "SpendenBeleg")
    if not Beleg.objects.exists():
        return
    index = {}
    for a in Adresse.objects.all():
        person = " ".join(t for t in (a.vorname, a.nachname) if t)
        name = (a.organisation or person) if a.art == "organisation" else (person or a.organisation)
        index.setdefault(namen.schluessel(name, a.plz), a.pk)
    kontakte = {k.such_name: k for k in Kontakt.objects.all()}
    nach_nummer = {s.belegnummer: s for s in Spende.objects.exclude(belegnummer="")}
    heute = timezone.localdate()
    for b in Beleg.objects.order_by("pk"):
        plz, ort = namen.plz_ort(b.plz_ort)
        schluessel = namen.schluessel(b.name, plz)
        if schluessel not in index:
            a = Adresse(**namen.teile(b.name), strasse=b.strasse, plz=plz, ort=ort,
                        geaendert_am=timezone.now(), geaendert_von=VON)  # fmt: skip
            k = kontakte.get(namen.normal(b.name))
            if k:
                a.email = k.email
                a.anrede = k.anrede if a.art == "person" else ""
                a.einwilligung_email = None if k.immer_post else heute
            a.save()
            index[schluessel] = a.pk
        datum, zweck = b.datum or _datum_aus_datei(b), ""
        if datum is None:
            datum, zweck = dt.date(b.jahr, 12, 31), "Spendendatum im Beleg nicht lesbar"
        spende = nach_nummer.get(b.belegnummer) if b.belegnummer else None
        fremd = "versendet" if b.im_portal_versendet else "offen"
        if spende is None:
            spende = Spende.objects.create(
                art="geld", adresse_id=index[schluessel], datum=datum, betrag=b.betrag,
                belegnummer=b.belegnummer, zweck=zweck, fremdbeleg=fremd,
                bedankt_am=b.bedankt_am, eingetragen_von=b.eingelesen_von or VON,
            )  # fmt: skip
            if b.belegnummer:
                nach_nummer[b.belegnummer] = spende
        elif not spende.fremdbeleg:
            spende.fremdbeleg = fremd
            spende.save(update_fields=["fremdbeleg"])
        _datei_verschieben(b.datei)
        SpendenBeleg.objects.create(
            adresse_id=spende.adresse_id, spende=spende, jahr=spende.datum.year,
            dateiname=b.dateiname, datei=b.datei, hochgeladen_von=b.eingelesen_von or VON,
            beigelegt_am=b.bedankt_am,
        )  # fmt: skip
    Beleg.objects.all().delete()  # alles übernommen; die Dateien liegen jetzt bei den Spenden


class Migration(migrations.Migration):
    dependencies = [
        ("vereinsportal", "0005_spendendatum"),
        ("spenden", "0005_fremdbeleg"),
        ("adressen", "0001_initial"),
    ]

    # Zurück (ältere Version): Die Spenden bleiben im Spendenpool, die alte Tabelle bleibt leer.
    operations = [migrations.RunPython(in_den_pool, migrations.RunPython.noop)]
