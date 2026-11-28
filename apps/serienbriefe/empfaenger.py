"""Empfänger für Serienbriefe (ADR 0047) und Platzhalter.

Empfänger wählt man in einem Feld mit Häkchen (``wahl()``): feste Gruppen (Mitglieder,
Ehrenamtliche, Angestellte, ehemalige Ehrenamtliche, Spender eines Jahres, Kunden mit eigenem
Recht) und darunter die Kategorien des Adressbuchs. Mehrere zusammen ergeben eine Liste, jeder
steht darin nur einmal (``zusammen()``). Auf Wunsch zählt für Adresskategorien, Spender und die
zusammengestellte Liste nur, wer eingewilligt hat (Post bzw. E-Mail); Mitglieder, Mitarbeitende
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
    ("ehrenamtliche", "Ehrenamtliche"),
    ("angestellte", "Angestellte"),
    ("ehemalige", "Ehemalige Ehrenamtliche"),
    ("spender", "Spender eines Jahres"),
    ("kunden", "Kunden (Haushalte)"),
    # nur zur Wahl, solange eine Liste aus dem Adressbuch mitgebracht wurde (``LISTE_SITZUNG``)
    ("liste", "Zusammengestellte Liste aus dem Adressbuch"),
]
# Unter diesem Namen liegen die Adressen einer im Adressbuch zusammengestellten Liste in der
# Sitzung – für diesen einen Brief, nichts wird dauerhaft gespeichert.
LISTE_SITZUNG = "serienbrief_liste"
LISTE_HOECHSTENS = 2000
# Feste Gruppen im Feld „Empfänger“, in dieser Reihenfolge; „adressen“ steht dort nicht, an
# seiner Stelle jede Adresskategorie einzeln als „kat:<pk>“.
GRUPPEN = ("mitglieder", "ehrenamtliche", "angestellte", "ehemalige", "spender", "kunden")
KATEGORIE = "kat:"
# Adresskategorien, die genauso heißen wie eine feste Gruppe, stehen nicht noch einmal zur Wahl
DOPPELT = {"mitglieder", "spender"}


def wahl(kunden: bool = False, liste: int = 0) -> list[tuple[str, str]]:
    """Was im Feld „Empfänger“ zum Anhaken steht: die festen Gruppen (Kunden nur mit dem Recht
    dazu), eine mitgebrachte Liste aus dem Adressbuch (``liste`` = Zahl der Adressen) und alle
    aktiven Adresskategorien."""
    from apps.adressen.models import AdressKategorie

    namen = dict(QUELLEN)
    erg = [(g, namen[g]) for g in GRUPPEN if g != "kunden" or kunden]
    if liste:
        erg.append(("liste", f"{namen['liste']} ({liste} Adresse{'' if liste == 1 else 'n'})"))
    erg += [
        (f"{KATEGORIE}{k.pk}", k.name)
        for k in AdressKategorie.objects.filter(aktiv=True)
        if k.name.strip().lower() not in DOPPELT
    ]
    return erg


def zusammen(gewaehlt: list[str], d: dict, benutzer=None) -> list["Empfaenger"]:
    """Die Empfänger aller angehakten Gruppen und Kategorien als eine Liste. Wer mehrfach
    vorkommt, steht einmal darin – mit den Angaben der zuerst genannten Gruppe (so behält ein
    Mitglied Mitgliedsnummer und Beitrag, auch wenn es zusätzlich Spender ist)."""
    from apps.adressen.models import AdressKategorie

    erg, gesehen = [], set()

    def dazu(liste):
        for e in liste:
            if e.schluessel not in gesehen:
                gesehen.add(e.schluessel)
                erg.append(e)

    for g in (*GRUPPEN, "liste"):
        if g in gewaehlt:
            dazu(suchen(g, d, benutzer))
    pks = [w[len(KATEGORIE) :] for w in gewaehlt if w.startswith(KATEGORIE)]
    kategorien = AdressKategorie.objects.filter(pk__in=[p for p in pks if p.isdigit()])
    if kategorien:  # ohne Kategorie hieße die Suche „alle Adressen“
        dazu(suchen("adressen", d | {"kategorien": kategorien}, benutzer))
    return erg


PLATZHALTER = [
    ("anrede", "Briefanrede, z. B. „Sehr geehrte Frau Muster,“"),
    ("anrede_du", "persönliche Anrede mit Vornamen: „Liebe Erika,“ bzw. „Lieber Max,“"),
    ("name", "ganzer Name bzw. Organisation"), ("vorname", "Vorname"), ("nachname", "Nachname"),
    ("organisation", "Organisation"), ("mitgliedsnummer", "Mitgliedsnummer"),
    ("jahresbeitrag", "Jahresbeitrag"), ("beitrag_offen", "offener Beitrag im gewählten Jahr"),
    ("spendensumme", "Geldspenden im gewählten Jahr"),
    ("anzahl_spenden", "Anzahl der Spenden (Dankesbriefe)"),
    ("spendendaten", "Daten der Spenden, z. B. „15.01.2026, 15.02.2026“ (Dankesbriefe)"),
    ("kundennummer", "Kundennummer"),
    ("alter", "Alter am Geburtstag (nur im Glückwunsch zum Geburtstag)"),
    ("jahr", "gewähltes Jahr"), ("datum", "heutiges Datum"), ("tafel", "Name der Tafel"),
]  # fmt: skip

# Verständliche Namen für die Kärtchen neben dem Editor und die Felder im Text (ADR 0088)
NAMEN = {
    "anrede": "Briefanrede", "anrede_du": "Liebe/Lieber + Vorname",
    "name": "Ganzer Name", "vorname": "Vorname", "nachname": "Nachname",
    "organisation": "Organisation", "mitgliedsnummer": "Mitgliedsnummer",
    "jahresbeitrag": "Jahresbeitrag", "beitrag_offen": "Offener Beitrag",
    "spendensumme": "Spendensumme", "anzahl_spenden": "Anzahl Spenden",
    "spendendaten": "Spendendaten", "kundennummer": "Kundennummer", "alter": "Alter",
    "jahr": "Jahr",
    "datum": "Heutiges Datum", "tafel": "Name der Tafel",
}  # fmt: skip
# Erfundener Empfänger für die Vorschau beim Bearbeiten einer Vorlage
BEISPIEL = {
    "anrede": "Sehr geehrte Frau Beispiel,", "anrede_du": "Liebe Erika,",
    "name": "Erika Beispiel", "vorname": "Erika",
    "nachname": "Beispiel", "organisation": "", "mitgliedsnummer": "42",
    "jahresbeitrag": "36,00 €", "beitrag_offen": "36,00 €", "spendensumme": "150,00 €",
    "anzahl_spenden": "2", "spendendaten": "15.01., 15.06.", "kundennummer": "1234",
    "alter": "60",
}  # fmt: skip
BEISPIEL_ANSCHRIFT = ["Frau Erika Beispiel", "Musterweg 1", "12345 Musterstadt"]

BEITRAGS_PLATZHALTER = {"jahresbeitrag", "beitrag_offen"}


def platzhalter() -> list[tuple[str, str]]:
    """Die angebotenen Platzhalter; ohne Mitgliedsbeiträge (ADR 0046) ohne die Beitragsfelder."""
    from apps.mitglieder.models import MitgliederEinstellungen

    if MitgliederEinstellungen.mit_beitraegen():
        return PLATZHALTER
    return [p for p in PLATZHALTER if p[0] not in BEITRAGS_PLATZHALTER]


def karten() -> list[tuple[str, str, str]]:
    """(Schlüssel, Name, Erklärung) der angebotenen Platzhalter für die Kärtchen."""
    return [(k, NAMEN.get(k, k), erklaerung) for k, erklaerung in platzhalter()]


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


def anrede_du(anrede: str, vorname: str, nachname: str, organisation: bool) -> str:
    """Persönliche Anrede mit Vornamen: „Liebe Erika,“ / „Lieber Max,“ nach der Anrede.

    Ohne Anrede (Frau/Herr) lässt sich „Liebe“ oder „Lieber“ nicht sicher wählen: dann „Hallo
    Kim,“. Ohne Vornamen oder bei Organisationen bleibt es bei der förmlichen Briefanrede.
    """
    vorname = (vorname or "").strip()
    if organisation or not vorname:
        return briefanrede(anrede, vorname, nachname, organisation)
    if anrede == "Frau":
        return f"Liebe {vorname},"
    if anrede == "Herr":
        return f"Lieber {vorname},"
    return f"Hallo {vorname},"


def allgemein(jahr: int) -> dict:
    """Alle bekannten Platzhalter (leer, wo sie für den Empfänger nicht passen)."""
    from apps.core.models import TafelEinstellungen

    werte = {name: "" for name, _ in PLATZHALTER}
    werte |= {"jahr": jahr, "datum": f"{timezone.localdate():%d.%m.%Y}",
              "tafel": TafelEinstellungen.laden().name}  # fmt: skip
    return werte


def aus_adresse(a, jahr: int, **mehr) -> "Empfaenger":
    """Empfänger aus einer Adresse des Adressbuchs; ``mehr`` sind zusätzliche Platzhalter."""
    return _aus_adresse(a, jahr, **mehr)


def _aus_adresse(a, jahr: int, **mehr) -> Empfaenger:
    from apps.spenden.models import Spende

    org = a.art == a.Art.ORGANISATION
    summe = a.spenden.filter(art=Spende.Art.GELD, datum__year=jahr).aggregate(s=Sum("betrag"))
    werte = {
        "anrede": briefanrede("" if org else a.anrede, a.vorname, a.nachname, org),
        "anrede_du": anrede_du("" if org else a.anrede, a.vorname, a.nachname, org),
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
    einwilligung = d.get("nur_einwilligung", False)
    ergebnis = []
    if quelle in ("adressen", "spender", "liste"):
        adressen = Adresse.objects.prefetch_related("kategorien")
        if quelle == "adressen":
            if d.get("kategorien"):
                adressen = adressen.filter(kategorien__in=d["kategorien"])
        elif quelle == "liste":
            adressen = adressen.filter(pk__in=d.get("liste_ids") or [])
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
    elif quelle == "angestellte":
        # wie die Liste „Angestellte“ unter „Verein/Team“: aktive Konten mit fester Beschäftigung
        adressen = Adresse.objects.filter(konto__is_active=True, konto__stelle__isnull=True,
                                          konto__beschaeftigung="fest")  # fmt: skip
        ergebnis = [_aus_adresse(a, jahr) for a in adressen.order_by("nachname", "vorname")]
    elif quelle in ("ehrenamtliche", "ehemalige"):
        # wie die Listen unter „Verein/Team“ (ADR 0098); kein Einwilligungs-Filter – wer mitmacht
        # oder mitgemacht hat, steht wie ein Mitglied in einer Beziehung zur Tafel
        from apps.konten.verwaltung import EHEMALIGE_KATEGORIE

        ehrenamt = Q(konto__stelle__isnull=True, konto__beschaeftigung="ehrenamtlich")
        ehemalig = Q(kategorien__name=EHEMALIGE_KATEGORIE)
        if quelle == "ehrenamtliche":
            pks = Adresse.objects.filter(ehrenamt, konto__is_active=True).exclude(
                pk__in=Adresse.objects.filter(ehemalig).values("pk")
            )
        else:
            pks = Adresse.objects.filter(ehemalig | (ehrenamt & Q(konto__is_active=False)))
        adressen = Adresse.objects.filter(pk__in=pks.values("pk"))
        ergebnis = [_aus_adresse(a, jahr) for a in adressen.order_by("nachname", "vorname")]
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
                     "anrede_du": anrede_du(p.anrede if p else "", vorname, nachname, False),
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
