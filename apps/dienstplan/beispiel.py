"""Beispiel-Dienstplan zum Ausprobieren (ADR 0077): Aufgaben wie auf dem Papierplan einer
Freitags-Ausgabe, dazu Montag und Mittwoch, alle Plätze mit erfundenen Namen besetzt.

Die erfundenen Helfer haben kein Konto und tragen ``KENNUNG`` in der Anmerkung; ``entfernen()``
löscht nur sie und ihre Besetzung, nie echte Helfer.
"""

import contextlib
import datetime as dt
import random

from django.db import transaction
from django.db.models import ProtectedError

from apps.adressen.models import Adresse
from apps.dienstplan.models import Aufgabe, Besetzung, DienstStelle, Diensttag
from apps.dienstplan.plan import STANDARD_AUFGABEN
from apps.kunden.models import Ausgabestelle

KENNUNG = "Beispiel (erfunden)"
STELLE = "Beispiel-Ausgabestelle"
AUFGABEN = STANDARD_AUFGABEN  # wie auf dem Papierplan
VORNAMEN = ["Anna", "Ben", "Carla", "David", "Elif", "Frank", "Greta", "Hakan", "Ines", "Jonas",
            "Klara", "Lars", "Mira", "Nils", "Olga", "Paul", "Rosa", "Sami", "Tanja", "Udo",
            "Vera", "Willi", "Yara", "Zoe"]  # fmt: skip
NACHNAMEN = ["Muster", "Beispiel", "Probe", "Sommer", "Winter", "Feld", "Berg", "Brook", "Ufer",
             "Stein", "Linde", "Wald"]  # fmt: skip
TAGE = ["Mo", "Mi", "Fr"]


def _zeit(text):
    return dt.time.fromisoformat(text)


def vorhanden() -> bool:
    return Adresse.objects.filter(notiz=KENNUNG, helfer=True).exists()


def anlegen(seed: int | None = None) -> dict:
    """Legt die Beispiel-Ausgabestelle mit Mo/Mi/Fr, allen Aufgaben und erfundenen Helfern an und
    verteilt sie zufällig (je Tag niemand doppelt). Wiederholbar."""
    zufall = random.Random(seed)  # noqa: S311 – Beispieldaten, kein Geheimnis
    with transaction.atomic():
        entfernen()
        stelle, _ = Ausgabestelle.objects.get_or_create(name=STELLE)
        ds, _ = DienstStelle.objects.update_or_create(
            ausgabestelle=stelle, defaults={"aktiv": True, "tage": ", ".join(TAGE)}
        )
        ds.aufgaben.all().delete()
        namen = [(v, n) for v in VORNAMEN for n in NACHNAMEN]
        zufall.shuffle(namen)
        pro_tag = sum(a[3] for a in AUFGABEN)
        helfer = [Adresse.objects.create(art=Adresse.Art.PERSON, vorname=v, nachname=n,
                                         notiz=KENNUNG, helfer=True, helfer_aktiv=True,
                                         telefon=f"0123 45{i:04d}")  # erfunden
                  for i, (v, n) in enumerate(namen[:pro_tag + 6])]  # fmt: skip
        anzahl = 0
        for tag in TAGE:
            frei = zufall.sample(helfer, len(helfer))
            reihenfolge = 0
            for name, von, bis, wie_oft, pflicht in AUFGABEN:
                for _ in range(wie_oft):
                    reihenfolge += 1
                    a = Aufgabe.objects.create(
                        stelle=ds,
                        wochentag=tag,
                        name=name,
                        von=_zeit(von),
                        bis=_zeit(bis),
                        reihenfolge=reihenfolge,
                        pflicht=pflicht,
                    )
                    anzahl += 1
                    if pflicht or zufall.random() < 0.5:
                        Besetzung.objects.create(aufgabe=a, helfer=frei.pop())
            leitung = Besetzung.objects.filter(aufgabe__stelle=ds, aufgabe__wochentag=tag,
                                               aufgabe__name="Teamleitung").first()  # fmt: skip
            Diensttag.objects.update_or_create(
                stelle=ds,
                wochentag=tag,
                defaults={"teamleitung": leitung.helfer if leitung else None},
            )
    return {"stelle": STELLE, "aufgaben": anzahl, "helfer": len(helfer)}


def entfernen() -> int:
    """Löscht die erfundenen Helfer (mit ihrer Besetzung) und die leere Beispiel-Ausgabestelle."""
    with transaction.atomic():
        anzahl = (Adresse.objects.filter(notiz=KENNUNG, helfer=True)
                  .delete()[1].get("adressen.Adresse", 0))  # fmt: skip
        stelle = Ausgabestelle.objects.filter(name=STELLE).first()
        if stelle and not stelle.kundengruppe_set.exists():
            with contextlib.suppress(ProtectedError):  # inzwischen anderweitig benutzt: bleibt
                stelle.delete()
    return anzahl
