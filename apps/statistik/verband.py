"""Verbandsstatistik (Abfrage des Tafel-Dachverbands, jedes Jahr im August): Kund:innen,
Haushalte und Tafel-Aktive in einem Stichmonat, mit Vergleich zum Vorjahresmonat.

Gezählt werden Haushalte mit mindestens einer Abholung im Stichmonat, jeder nur einmal, und alle
Personen dieser Haushalte. Alter am letzten Tag des Stichmonats. Die Zusammensetzung der Haushalte
ist der heutige Stand (bintafeln merkt sich nicht, wer früher zum Haushalt gehörte); gelöschte
Haushalte und Abholungen nach Ablauf der Löschfrist fehlen. Nur Summen, keine Personendaten.
"""

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model

from apps.kunden.models import Abholung, Haushalt, KundenEinstellungen, abholfrist_beginn

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]  # fmt: skip
KIND_BIS = 17  # unter 18 Jahren
SENIOR_AB = 63
JUNG_BIS = 35
# Stufen des Vergleichs mit dem Vorjahr wie im Fragebogen des Verbands
LEGENDE = [
    (-3, "mindestens 25 % weniger"),
    (-2, "zwischen 15 und weniger als 25 % weniger"),
    (-1, "zwischen 5 und weniger als 15 % weniger"),
    (0, "mehr oder weniger gleich viel (+/- 5 %)"),
    (1, "zwischen 5 und weniger als 15 % mehr"),
    (2, "zwischen 15 und weniger als 25 % mehr"),
    (3, "mindestens 25 % mehr"),
]


def stufe(prozent: float) -> int:
    """Veränderung in Prozent → Stufe −3 … +3 (Grenzen wie im Fragebogen)."""
    if prozent <= -25:
        return -3
    if prozent <= -15:
        return -2
    if prozent <= -5:
        return -1
    if prozent < 5:
        return 0
    if prozent < 15:
        return 1
    if prozent < 25:
        return 2
    return 3


def _alter(geburtsdatum: dt.date, stichtag: dt.date) -> int:
    vorher = (stichtag.month, stichtag.day) < (geburtsdatum.month, geburtsdatum.day)
    return stichtag.year - geburtsdatum.year - vorher


def _monatsende(jahr: int, monat: int) -> dt.date:
    erster = dt.date(jahr + (monat == 12), monat % 12 + 1, 1)
    return erster - dt.timedelta(days=1)


def _prozent(teil: int, ganzes: int) -> float | None:
    return round(100 * teil / ganzes, 2) if ganzes else None


@dataclass
class Monat:
    """Zahlen eines Stichmonats."""

    jahr: int
    monat: int
    haushalte: int = 0
    personen: int = 0
    kinder: int = 0
    erwachsene: int = 0  # ab 18
    mittlere: int = 0  # 18 bis 62
    senioren: int = 0  # ab 63
    ohne_geburtsdatum: int = 0
    staaten: list[tuple[str, int]] = field(default_factory=list)
    ukraine: int = 0
    einkommen: list[tuple[str, int]] = field(default_factory=list)
    vollstaendig: bool = True  # False: Abholungen schon nach der Löschfrist gelöscht

    @property
    def name(self) -> str:
        return f"{MONATE[self.monat - 1]} {self.jahr}"

    @property
    def stichtag(self) -> dt.date:
        return _monatsende(self.jahr, self.monat)


def monat(jahr: int, monat_nr: int, stellen=None) -> Monat:
    m = Monat(jahr, monat_nr)
    erster = dt.date(jahr, monat_nr, 1)
    m.vollstaendig = erster >= abholfrist_beginn()
    abholungen = Abholung.objects.filter(datum__range=(erster, m.stichtag))
    if stellen is not None:
        abholungen = abholungen.filter(ausgabestelle__in=stellen)
    haushalte = (Haushalt.objects.filter(pk__in=abholungen.values("haushalt_id"))
                 .select_related("einkommensart").prefetch_related("personen"))  # fmt: skip
    staaten, einkommen = Counter(), Counter()
    for h in haushalte:
        m.haushalte += 1
        einkommen[h.einkommensart.bezeichnung if h.einkommensart_id else "nicht angegeben"] += 1
        for p in h.personen.all():
            m.personen += 1
            staat = (p.staatsangehoerigkeit or "").strip() or "nicht angegeben"
            staaten[staat] += 1
            if "ukrain" in staat.lower():
                m.ukraine += 1
            if p.geburtsdatum is None:
                m.ohne_geburtsdatum += 1
                continue
            alter = _alter(p.geburtsdatum, m.stichtag)
            if alter <= KIND_BIS:
                m.kinder += 1
            else:
                m.erwachsene += 1
                if alter >= SENIOR_AB:
                    m.senioren += 1
                else:
                    m.mittlere += 1
    m.staaten = staaten.most_common()
    m.einkommen = einkommen.most_common()
    return m


@dataclass
class Aktive:
    gesamt: int = 0
    ehrenamtlich: int = 0
    beschaeftigt: int = 0
    ehrenamt_ab_63: int = 0
    ehrenamt_bis_35: int = 0
    ehrenamt_weiblich: int = 0
    ohne_geburtsdatum: int = 0
    selbst_kunden: int = 0


def aktive(stichtag: dt.date) -> Aktive:
    """Tafel-Aktive: aktive Konten von Personen (ohne Konten der Ausgabestellen). „Selbst
    Kund:in“: gleicher Vor- und Nachname und gleiches Geburtsdatum wie eine Person in einem
    nicht beendeten Haushalt."""
    from apps.kunden.models import Person

    a = Aktive()
    kunden = {
        (v.strip().lower(), n.strip().lower(), g)
        for v, n, g in Person.objects.exclude(haushalt__status=Haushalt.Status.BEENDET)
        .exclude(geburtsdatum=None).values_list("vorname", "nachname", "geburtsdatum")
    }  # fmt: skip
    benutzer = get_user_model()
    for b in benutzer.objects.filter(is_active=True, stelle__isnull=True).select_related(
            "stammdaten"):  # fmt: skip
        stamm = getattr(b, "stammdaten", None)
        geburt = stamm.geburtsdatum if stamm else None
        a.gesamt += 1
        if geburt and (b.first_name.strip().lower(), b.last_name.strip().lower(), geburt) in kunden:
            a.selbst_kunden += 1
        if b.beschaeftigung != benutzer.Beschaeftigung.EHRENAMTLICH:
            a.beschaeftigt += 1
            continue
        a.ehrenamtlich += 1
        if stamm and stamm.anrede.strip().lower() == "frau":
            a.ehrenamt_weiblich += 1
        if geburt is None:
            a.ohne_geburtsdatum += 1
        elif _alter(geburt, stichtag) >= SENIOR_AB:
            a.ehrenamt_ab_63 += 1
        elif _alter(geburt, stichtag) <= JUNG_BIS:
            a.ehrenamt_bis_35 += 1
    return a


@dataclass
class Frage:
    nummer: str
    text: str
    kopf: list[str]
    zeilen: list[list]
    hinweis: str = ""
    vergleich: bool = False  # Zeilen mit Stufen −3 … +3


def _zeile(text, zahl, ganzes):
    p = _prozent(zahl, ganzes)
    return [text, zahl, f"{p:.2f} %".replace(".", ",") if p is not None else "–"]


def _vergleich(text, jetzt: int, vorher: int, moeglich: bool) -> list:
    if not moeglich or not vorher:
        return [text, vorher if moeglich else "–", jetzt, "–", None]
    p = round(100 * (jetzt - vorher) / vorher, 2)
    return [text, vorher, jetzt, f"{p:+.2f} %".replace(".", ","), stufe(p)]


def fragen(jahr: int, monat_nr: int = 6, stellen=None) -> tuple[Monat, Monat, list[Frage]]:
    jetzt = monat(jahr, monat_nr, stellen)
    vorher = monat(jahr - 1, monat_nr, stellen)
    j, v = jetzt.name, vorher.name
    kind = f"vor dem {jetzt.stichtag.replace(year=jetzt.stichtag.year - KIND_BIS - 1):%d.%m.%Y}"
    senior = f"vor dem {jetzt.stichtag.replace(year=jetzt.stichtag.year - SENIOR_AB):%d.%m.%Y}"
    ohne = (f" {jetzt.ohne_geburtsdatum} Personen ohne Geburtsdatum sind bei den Altersgruppen "
            "nicht mitgezählt." if jetzt.ohne_geburtsdatum else "")  # fmt: skip
    vergleich_ok = vorher.vollstaendig
    a = aktive(jetzt.stichtag)
    liste = [
        Frage("2.1", f"Anzahl der direkten Kund:innen insgesamt, einschließlich der im Haushalt "
              f"mitversorgten Kinder und Erwachsenen, im {j}", ["", "Anzahl"],
              [["Kund:innen insgesamt", jetzt.personen]],
              f"{jetzt.haushalte} Haushalte mit insgesamt {jetzt.personen} Personen, die "
              f"mindestens eine Abholung im {j} hatten. Jeder Haushalt zählt nur einmal, auch "
              "bei mehreren Abholungen im Monat."),
        Frage("2.3", f"Wie viele der {jetzt.personen} Kund:innen im {j} waren:",
              ["", "Anzahl", "Anteil"],
              [_zeile("Kinder und Jugendliche unter 18 Jahren", jetzt.kinder, jetzt.personen),
               _zeile("Erwachsene ab 18 Jahren", jetzt.erwachsene, jetzt.personen)],
              f"Alter am {jetzt.stichtag:%d.%m.%Y}; Erwachsene: geboren {kind}." + ohne),
        Frage("2.4", f"Wie viele der {jetzt.erwachsene} erwachsenen Kund:innen im {j} waren "
              f"Senior:innen ab {SENIOR_AB} Jahren:", ["", "Anzahl", "Anteil"],
              [_zeile(f"Senior:innen ab {SENIOR_AB} Jahren", jetzt.senioren, jetzt.erwachsene)],
              f"Geboren {senior}. Der Anteil bezieht sich auf die {jetzt.erwachsene} "
              "Erwachsenen."),
        Frage("2.5", f"Wie viele der {jetzt.personen} Kund:innen im {j} waren:",
              ["", "Anzahl", "Anteil"],
              [_zeile("Kinder und Jugendliche unter 18 Jahren", jetzt.kinder, jetzt.personen),
               _zeile(f"Erwachsene von 18 bis {SENIOR_AB - 1} Jahren", jetzt.mittlere,
                      jetzt.personen),
               _zeile(f"Senior:innen ab {SENIOR_AB} Jahren", jetzt.senioren, jetzt.personen)],
              f"Der Anteil bezieht sich auf alle {jetzt.personen} Personen." + ohne),
        Frage("2.6", f"Wie viele der {jetzt.personen} Kund:innen im {j} waren Geflüchtete aus "
              "der Ukraine:", ["", "Anzahl", "Anteil"],
              [_zeile("Staatsangehörigkeit Ukraine", jetzt.ukraine, jetzt.personen)],
              "Gezählt nach Staatsangehörigkeit. Alle Staatsangehörigkeiten in der Tabelle "
              "darunter."),
        Frage("2.6a", f"Staatsangehörigkeiten der Kund:innen im {j}", ["", "Anzahl", "Anteil"],
              [_zeile(s, n, jetzt.personen) for s, n in jetzt.staaten]),
        Frage("2.7", f"Hatte Ihre Tafel im {j} mehr, weniger oder gleich viele Kund:innen "
              f"verglichen mit dem {v}?", ["", v, j, "Veränderung", "Stufe"],
              [_vergleich("Kund:innen insgesamt", jetzt.personen, vorher.personen, vergleich_ok),
               _vergleich("Kinder und Jugendliche", jetzt.kinder, vorher.kinder, vergleich_ok),
               _vergleich(f"Erwachsene (18 bis {SENIOR_AB - 1})", jetzt.mittlere,
                          vorher.mittlere, vergleich_ok),
               _vergleich("Senior:innen", jetzt.senioren, vorher.senioren, vergleich_ok)],
              vergleich=True),
        Frage("3.1", f"Anzahl der Kund:innen-Haushalte/Bedarfsgemeinschaften im {j}",
              ["", "Anzahl"], [["Kund:innen-Haushalte", jetzt.haushalte]],
              f"Haushalte mit mindestens einer Abholung im {j}."),
        Frage("3.2", f"Wie viele der {jetzt.haushalte} Kund:innen-Haushalte im {j} waren:",
              ["Einkommensart", "Anzahl", "Anteil"],
              [_zeile(e, n, jetzt.haushalte) for e, n in jetzt.einkommen],
              "Nach der Einkommensart am Haushalt (heutiger Stand). Die Kategorien des "
              "Fragebogens bitte zuordnen."),
        Frage("3.3", f"Hatte Ihre Tafel im {j} mehr, weniger oder gleich viele "
              f"Kund:innen-Haushalte verglichen mit dem {v}?",
              ["", v, j, "Veränderung", "Stufe"],
              [_vergleich("Haushalte insgesamt", jetzt.haushalte, vorher.haushalte,
                          vergleich_ok)]
              + [_vergleich(e, dict(jetzt.einkommen).get(e, 0), dict(vorher.einkommen).get(e, 0),
                            vergleich_ok)
                 for e in dict.fromkeys([e for e, _ in jetzt.einkommen + vorher.einkommen])],
              vergleich=True),
        Frage("5.1", f"Anzahl der Tafel-Aktiven (Ehrenamtliche und Beschäftigte) im {j}",
              ["", "Anzahl"],
              [["Tafel-Aktive gesamt", a.gesamt],
               ["davon Ehrenamtliche", a.ehrenamtlich],
               ["davon Beschäftigte (fest angestellt)", a.beschaeftigt],
               [f"Ehrenamtliche ab {SENIOR_AB} Jahren", a.ehrenamt_ab_63],
               [f"Ehrenamtliche bis {JUNG_BIS} Jahre", a.ehrenamt_bis_35],
               ["weibliche Ehrenamtliche (Anrede „Frau“)", a.ehrenamt_weiblich],
               ["Tafel-Aktive, die selbst Kund:innen sind", a.selbst_kunden]],
              "Heutiger Stand der aktiven Konten (ohne Konten der Ausgabestellen)."
              + (f" {a.ohne_geburtsdatum} Ehrenamtliche ohne Geburtsdatum fehlen bei den "
                 "Altersangaben." if a.ohne_geburtsdatum else "")
              + " „Selbst Kund:in“: gleicher Name und gleiches Geburtsdatum wie eine Person im "
              "Kundenstamm."),
    ]  # fmt: skip
    if not vergleich_ok:
        for f in liste:
            if f.vergleich:
                f.hinweis = (f"Abholungen aus dem {v} sind nach der Löschfrist schon gelöscht "
                             "(Einstellungen → Kundenstamm); ein Vergleich ist nicht "
                             "möglich.")  # fmt: skip
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    if kind_bis != KIND_BIS:
        liste[1].hinweis += (f" (Der Verband fragt nach unter 18 Jahren; sonst zählt bintafeln "
                             f"bis {kind_bis} Jahre als Kind.)")  # fmt: skip
    return jetzt, vorher, liste
