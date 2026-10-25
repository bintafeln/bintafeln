"""Empfänger für Serienbriefe (ADR 0047) und Platzhalter.

Quellen: Adressen nach Kategorie, Mitglieder, Spender eines Jahres, Kunden (eigenes Recht).
Für Adressen und Spender zählt die Einwilligung (Post bzw. E-Mail) aus dem Adressbuch; Mitglieder
und Kunden stehen in einem Vertrags- bzw. Betreuungsverhältnis mit der Tafel.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

QUELLEN = [
    ("adressen", "Adressen nach Kategorie"),
    ("mitglieder", "Mitglieder"),
    ("spender", "Spender eines Jahres"),
    ("kunden", "Kunden (Haushalte)"),
]
PLATZHALTER = [
    ("anrede", "Briefanrede, z. B. „Sehr geehrte Frau Muster,“"),
    ("name", "ganzer Name bzw. Organisation"), ("vorname", "Vorname"), ("nachname", "Nachname"),
    ("organisation", "Organisation"), ("mitgliedsnummer", "Mitgliedsnummer"),
    ("jahresbeitrag", "Jahresbeitrag"), ("beitrag_offen", "offener Beitrag im gewählten Jahr"),
    ("spendensumme", "Geldspenden im gewählten Jahr"),
    ("anzahl_spenden", "Anzahl der Spenden (Dankesbriefe)"),
    ("spendendaten", "Daten der Spenden, z. B. „15.01.2026, 15.02.2026“ (Dankesbriefe)"),
    ("kundennummer", "Kundennummer"),
    ("jahr", "gewähltes Jahr"), ("datum", "heutiges Datum"), ("tafel", "Name der Tafel"),
]  # fmt: skip


BEITRAGS_PLATZHALTER = {"jahresbeitrag", "beitrag_offen"}


def platzhalter() -> list[tuple[str, str]]:
    """Die angebotenen Platzhalter; ohne Mitgliedsbeiträge (ADR 0046) ohne die Beitragsfelder."""
    from apps.mitglieder.models import MitgliederEinstellungen

    if MitgliederEinstellungen.mit_beitraegen():
        return PLATZHALTER
    return [p for p in PLATZHALTER if p[0] not in BEITRAGS_PLATZHALTER]


@dataclass
class Empfaenger:
    schluessel: str
    name: str
    anschrift: list[str]
    email: str = ""
    werte: dict = field(default_factory=dict)


def _euro(betrag) -> str:
    return f"{Decimal(betrag or 0):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def briefanrede(anrede: str, vorname: str, nachname: str, organisation: bool) -> str:
    if anrede == "Frau" and nachname:
        return f"Sehr geehrte Frau {nachname},"
    if anrede == "Herr" and nachname:
        return f"Sehr geehrter Herr {nachname},"
    if not organisation and nachname:
        return f"Guten Tag {' '.join(t for t in (vorname, nachname) if t)},"
    return "Sehr geehrte Damen und Herren,"


def _aus_adresse(a, jahr: int, **mehr) -> Empfaenger:
    from apps.spenden.models import Spende

    org = a.art == a.Art.ORGANISATION
    summe = a.spenden.filter(art=Spende.Art.GELD, datum__year=jahr).aggregate(s=Sum("betrag"))
    werte = {
        "anrede": briefanrede("" if org else a.anrede, a.vorname, a.nachname, org),
        "name": a.name, "vorname": a.vorname, "nachname": a.nachname,
        "organisation": a.organisation, "spendensumme": _euro(summe["s"]),
    } | mehr  # fmt: skip
    return Empfaenger(f"a:{a.pk}", a.name, a.anschrift_zeilen, a.email, werte)


def suchen(quelle: str, d: dict, benutzer=None) -> list[Empfaenger]:
    """``d`` = bereinigte Daten des Auswahlformulars."""
    from apps.adressen.models import Adresse
    from apps.mitglieder.models import Mitglied, MitgliederEinstellungen

    jahr = d.get("jahr") or timezone.localdate().year
    email = d.get("versandart") == "email"
    einwilligung = d.get("nur_einwilligung", True)
    ergebnis = []
    if quelle in ("adressen", "spender"):
        adressen = Adresse.objects.prefetch_related("kategorien")
        if quelle == "adressen":
            if d.get("kategorien"):
                adressen = adressen.filter(kategorien__in=d["kategorien"])
        else:
            mindest = d.get("mindestbetrag") or Decimal("0.01")
            adressen = adressen.annotate(
                summe=Sum("spenden__betrag", filter=Q(spenden__art="geld",
                                                       spenden__datum__year=jahr))
            ).filter(summe__gte=mindest)  # fmt: skip
        if einwilligung:
            adressen = adressen.filter(**{("einwilligung_email" if email else
                                           "einwilligung_post") + "__isnull": False})  # fmt: skip
        ergebnis = [
            _aus_adresse(a, jahr) for a in adressen.distinct().order_by("organisation", "nachname")
        ]
    elif quelle == "mitglieder":
        heute = timezone.localdate()
        mitglieder = Mitglied.objects.select_related("adresse").filter(
            Q(austritt__isnull=True) | Q(austritt__gte=heute), eintritt__lte=heute
        )
        if d.get("mitgliedsarten"):
            mitglieder = mitglieder.filter(art__in=d["mitgliedsarten"])
        anteilig = MitgliederEinstellungen.laden().anteilig
        for m in mitglieder:
            offen = max(m.soll(jahr, anteilig) - m.gezahlt(jahr), Decimal("0"))
            if d.get("nur_offen") and not offen:
                continue
            ergebnis.append(_aus_adresse(m.adresse, jahr, mitgliedsnummer=m.nummer,
                                         jahresbeitrag=_euro(m.jahresbeitrag),
                                         beitrag_offen=_euro(offen)))  # fmt: skip
    elif quelle == "kunden":
        from apps.kunden import zugang
        from apps.kunden.models import Haushalt

        haushalte = Haushalt.objects.filter(status=Haushalt.Status.AKTIV).prefetch_related(
            "personen"
        )
        if benutzer is not None:
            haushalte = zugang.filtern(haushalte, benutzer)
        if d.get("kundengruppen"):
            haushalte = haushalte.filter(kundengruppe__in=d["kundengruppen"])
        for h in haushalte.order_by("kundennummer"):
            p = h.hauptperson
            vorname, nachname = (p.vorname, p.nachname) if p else ("", "")
            name = " ".join(t for t in (vorname, nachname) if t) or f"Haushalt {h.kundennummer}"
            zeilen = [" ".join(t for t in ((p.anrede if p else ""), name) if t), h.strasse,
                      " ".join(t for t in (h.plz, h.ort) if t)]  # fmt: skip
            werte = {"anrede": briefanrede(p.anrede if p else "", vorname, nachname, False),
                     "name": name, "vorname": vorname, "nachname": nachname,
                     "kundennummer": h.kundennummer}  # fmt: skip
            ergebnis.append(Empfaenger(f"k:{h.kundennummer}", name,
                                       [z for z in zeilen if z], h.email, werte))  # fmt: skip
    return ergebnis


def aufteilen(empfaenger: list[Empfaenger], versandart: str):
    """(erreichbar, ohne Anschrift bzw. E-Mail)."""
    if versandart == "email":
        return [e for e in empfaenger if e.email], [e for e in empfaenger if not e.email]
    ok = [e for e in empfaenger if len(e.anschrift) >= 3]  # Name, Straße, PLZ Ort
    return ok, [e for e in empfaenger if len(e.anschrift) < 3]


def einsetzen(text: str, e: Empfaenger, allgemein: dict) -> str:
    """Ersetzt {platzhalter}; Unbekanntes bleibt stehen, damit Tippfehler auffallen."""
    werte = allgemein | e.werte

    def ersetzen(treffer):
        wert = werte.get(treffer.group(1))
        return treffer.group(0) if wert is None else str(wert)

    return re.sub(r"\{(\w+)\}", ersetzen, text)
