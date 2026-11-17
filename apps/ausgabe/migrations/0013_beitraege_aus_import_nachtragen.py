"""Beiträge importierter Abholungen einmalig in die Kasse nachtragen.

Die Tagesliste aus dem bisherigen Programm brachte den Beitrag nur an der Abholung mit, ohne
Buchung – deshalb fehlte er in der Kasse. Für jede Abholung mit Beitrag und ohne Buchung entsteht
eine Bar-Buchung (Soll = Haben = Beitrag, der Kontostand ändert sich nicht), außer es gibt für
denselben Kunden am selben Tag schon eine Abholungs-Buchung (z. B. aus buchungen.csv).
Rückwärts werden genau diese Buchungen wieder entfernt (an der Anmerkung erkennbar).
"""

import datetime as dt

from django.db import migrations
from django.utils import timezone

ANMERKUNG = "Beitrag laut Import"


def nachtragen(apps, schema_editor):
    Abholung = apps.get_model("kunden", "Abholung")
    Buchung = apps.get_model("ausgabe", "Buchung")
    schon = set(Buchung.objects.filter(art="abholung").values_list("kundennummer", "datum"))
    mit_buchung = set(Buchung.objects.filter(abholung__isnull=False).values_list("abholung_id",
                                                                                 flat=True))
    neue = []
    for a in Abholung.objects.filter(beitrag__gt=0).select_related("haushalt").iterator():
        if a.pk in mit_buchung:
            continue
        schluessel = (a.haushalt.kundennummer, a.datum)
        if schluessel in schon:
            continue
        schon.add(schluessel)
        uhrzeit = a.uhrzeit or dt.time(12, 0)
        neue.append(Buchung(
            haushalt_id=a.haushalt_id, kundennummer=a.haushalt.kundennummer, datum=a.datum,
            zeitpunkt=timezone.make_aware(dt.datetime.combine(a.datum, uhrzeit)),
            art="abholung", zahlweise="bar", soll=a.beitrag, haben=a.beitrag, bar=a.beitrag,
            abholung_id=a.pk, ausgabestelle_id=a.ausgabestelle_id, bemerkung=ANMERKUNG,
            eingetragen_von=a.eingetragen_von, importiert=True,
        ))
    Buchung.objects.bulk_create(neue, batch_size=5000)


def entfernen(apps, schema_editor):
    apps.get_model("ausgabe", "Buchung").objects.filter(
        bemerkung=ANMERKUNG, importiert=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ausgabe", "0012_vorwarnung_wochen"),
        ("kunden", "0051_abholungen_ausgabestelle"),
    ]

    operations = [migrations.RunPython(nachtragen, entfernen)]
