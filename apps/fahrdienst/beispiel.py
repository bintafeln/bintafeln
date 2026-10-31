"""Beispiel-Fahrerplan zum Ausprobieren (ADR 0074): Touren wie auf dem bisherigen Papierplan und
erfundene Fahrer und Beifahrer, zufällig verteilt.

Die erfundenen Personen sind Adressen mit ``KENNUNG`` in der Notiz (kein Konto); ``entfernen()``
löscht nur sie samt Fahrdienst-Bezug, nie echte Leute.
"""

import random

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from apps.adressen.models import Adresse
from apps.ausgabe.ampel import wochentage
from apps.fahrdienst.models import Besetzung, FahrdienstEinstellungen, Springer, Tour
from apps.konten import rollen

KENNUNG = "Beispiel-Fahrdienst (erfunden)"
KONTO_PRAEFIX = "beispiel-fd-"
TOUREN = ["Katernberg", "Innenstadt", "Steele", "Frohnhausen", "Sondertour"]
FAHRER = ["Max Mustermann", "Lena Sommer", "Kai Nordmann", "Paul Winter", "Udo Feld",
          "Ina Kurz", "Rolf Stein", "Tom Brandt", "Gerd Lohmann"]  # fmt: skip
BEIFAHRER = ["Jan Beispiel", "Eva Lindner", "Ole Hansen", "Tim Weber", "Anna Berg", "Mia Roth",
             "Ben Vogel", "Lisa Kern", "Karl Ufer", "Nina Holt", "Rita Sand"]  # fmt: skip
SPRINGER = ["Sven Ersatz", "Petra Spring", "Uwe Helfer"]


def _person(name: str, rolle: str) -> Adresse:
    """Erfundene Person mit Konto und passender Rolle: ob jemand im Fahrdienst mitfährt (und ob
    als Fahrer oder Beifahrer), bestimmt die Rolle (ADR 0097)."""
    vorname, nachname = name.split()
    gruppe = rollen.FAHRER if rolle == "fahrer" else rollen.BEIFAHRER
    konto = get_user_model().objects.create(
        username=f"{KONTO_PRAEFIX}{vorname}-{nachname}".lower(),
        first_name=vorname, last_name=nachname, is_active=True,
    )  # fmt: skip
    konto.set_unusable_password()
    konto.save(update_fields=["password"])
    konto.groups.add(Group.objects.get_or_create(name=gruppe)[0])
    return Adresse.objects.create(art=Adresse.Art.PERSON, vorname=vorname, nachname=nachname,
                                  notiz=KENNUNG, konto=konto, helfer_aktiv=True,
                                  fahrdienst=rolle)  # fmt: skip


def vorhanden() -> bool:
    return Adresse.objects.filter(notiz=KENNUNG).exists()


def anlegen(seed: int | None = None) -> dict:
    """Legt die Touren (3 Plätze, mindestens 2) und erfundene Leute an und verteilt sie zufällig
    auf die Fahrtage; ein Platz für Gäste bleibt meist frei. Wiederholbar: Die feste Besetzung der
    Beispiel-Touren wird neu gewürfelt."""
    zufall = random.Random(seed)  # noqa: S311 – Beispieldaten, kein Geheimnis
    with transaction.atomic():
        entfernen()
        fahrer = [_person(n, "fahrer") for n in FAHRER]
        beifahrer = [_person(n, "beifahrer") for n in BEIFAHRER]
        springer = [_person(n, "beifahrer") for n in SPRINGER]
        for i, s in enumerate(springer):
            tage = "Mi" if i == 2 else ""  # einer nur mittwochs, wie auf dem Papierplan
            Springer.objects.get_or_create(person=s, defaults={"wochentage": tage})
        touren = []
        for i, name in enumerate(TOUREN):
            tour, _ = Tour.objects.update_or_create(
                name=name, defaults={"reihenfolge": i + 1, "plaetze": 3, "mindestbesetzung": 2,
                                     "aktiv": True})  # fmt: skip
            touren.append(tour)
        Besetzung.objects.filter(tour__in=touren).delete()
        anzahl = 0
        for tag in wochentage(FahrdienstEinstellungen.laden().fahrtage):
            freie_fahrer = zufall.sample(fahrer, len(fahrer))
            freie_beifahrer = zufall.sample(beifahrer, len(beifahrer))
            for tour in touren:
                leute = [freie_fahrer.pop(), freie_beifahrer.pop()]
                if freie_beifahrer and zufall.random() < 0.25:  # manchmal zu dritt
                    leute.append(freie_beifahrer.pop())
                for nr, b in enumerate(leute, start=1):
                    Besetzung.objects.create(tour=tour, wochentag=tag, platz=nr, person=b)
                    anzahl += 1
    return {"Touren": len(touren), "Personen": len(fahrer) + len(beifahrer) + len(springer),
            "Einteilungen": anzahl}  # fmt: skip


def entfernen() -> int:
    """Löscht die erfundenen Personen mit allem Fahrdienst-Bezug und die Beispiel-Touren, wenn sie
    keine echten Leute mehr enthalten."""
    with transaction.atomic():
        personen = Adresse.objects.filter(notiz=KENNUNG)
        anzahl = personen.count()
        personen.delete()  # Besetzung, Springer, Ausfälle, Ersatz hängen daran und gehen mit
        get_user_model().objects.filter(username__startswith=KONTO_PRAEFIX).delete()
        Tour.objects.filter(name__in=TOUREN, besetzungen__isnull=True).delete()
    return anzahl
