"""Zuwendungsbestätigungen (ADR 0045) nach den amtlichen Mustern (BMF-Schreiben zu § 10b EStG).

Ausstellen vergibt eine fortlaufende Nummer und verknüpft die Spenden, damit keine Spende zweimal
bestätigt wird. Das PDF entsteht jedes Mal neu aus den gespeicherten Daten; stornierte
Bestätigungen tragen den Vermerk „STORNIERT“.
"""

from django.db import transaction
from django.utils import timezone
from reportlab.platypus import PageBreak

from apps.core.models import TafelEinstellungen
from apps.core.pdf import Pdf
from apps.spenden.models import (
    Spende,
    SpendenEinstellungen,
    Zuwendungsbestaetigung,
    naechste_nummer,
    summe,
)
from apps.spenden.worte import euro

HAFTUNG = (
    "Hinweis: Wer vorsätzlich oder grob fahrlässig eine unrichtige Zuwendungsbestätigung erstellt "
    "oder veranlasst, dass Zuwendungen nicht zu den in der Zuwendungsbestätigung angegebenen "
    "steuerbegünstigten Zwecken verwendet werden, haftet für die entgangene Steuer (§ 10b Abs. 4 "
    "EStG, § 9 Abs. 3 KStG, § 9 Nr. 5 GewStG). Diese Bestätigung wird nicht als Nachweis für die "
    "steuerliche Berücksichtigung der Zuwendung anerkannt, wenn das Datum des "
    "Freistellungsbescheides länger als 5 Jahre bzw. das Datum der Feststellung der Einhaltung der "
    "satzungsmäßigen Voraussetzungen nach § 60a Abs. 1 AO länger als 3 Jahre seit Ausstellung "
    "des Bescheides zurückliegt (§ 63 Abs. 5 AO)."
)


class BestaetigungsFehler(ValueError):
    pass


def _bereit(e: SpendenEinstellungen) -> None:
    fehlt = e.fehlende_angaben()
    if fehlt:
        raise BestaetigungsFehler(
            "Für Zuwendungsbestätigungen fehlen noch Angaben unter „Einstellungen → Spenden“: "
            + ", ".join(fehlt)
            + "."
        )


def offene_geldspenden(adresse, jahr: int):
    """Geldspenden (und abziehbare Mitgliedsbeiträge) eines Jahres ohne gültige Bestätigung."""
    spenden = Spende.objects.filter(
        adresse=adresse, art=Spende.Art.GELD, datum__year=jahr, betrag__gt=0
    ).exclude(bestaetigung__isnull=False, bestaetigung__storniert_am__isnull=True)
    if not SpendenEinstellungen.laden().mitgliedsbeitraege_abziehbar:
        spenden = spenden.exclude(mitgliedsbeitrag=True)
    return spenden


def jahresliste(jahr: int) -> list[tuple]:
    """[(Adresse, Summe, Anzahl)] aller Spender mit noch nicht bestätigten Geldspenden."""
    from apps.adressen.models import Adresse

    ergebnis = []
    for a in Adresse.objects.filter(spenden__art=Spende.Art.GELD,
                                    spenden__datum__year=jahr).distinct():  # fmt: skip
        offen = offene_geldspenden(a, jahr)
        if offen.exists():
            ergebnis.append((a, summe(offen), offen.count()))
    return ergebnis


@transaction.atomic
def geld_ausstellen(adresse, jahr: int, von: str) -> Zuwendungsbestaetigung:
    """Eine Spende: Einzelbestätigung; mehrere: Sammelbestätigung für das Jahr."""
    _bereit(SpendenEinstellungen.laden())
    spenden = list(offene_geldspenden(adresse, jahr).select_for_update(of=("self",)))
    if not spenden:
        raise BestaetigungsFehler(f"{adresse.name} hat {jahr} keine unbestätigten Geldspenden.")
    art = Zuwendungsbestaetigung.Art.GELD if len(spenden) == 1 else (
        Zuwendungsbestaetigung.Art.SAMMEL)  # fmt: skip
    b = Zuwendungsbestaetigung.objects.create(
        nummer=naechste_nummer(), art=art, adresse=adresse, ausgestellt_am=timezone.localdate(),
        betrag=sum(s.betrag for s in spenden), ausgestellt_von=von,
    )  # fmt: skip
    Spende.objects.filter(pk__in=[s.pk for s in spenden]).update(bestaetigung=b)
    return b


@transaction.atomic
def sach_ausstellen(spende: Spende, von: str) -> Zuwendungsbestaetigung:
    _bereit(SpendenEinstellungen.laden())
    spende = Spende.objects.select_for_update().get(pk=spende.pk)
    if spende.art != Spende.Art.SACH:
        raise BestaetigungsFehler("Das ist keine Sachspende.")
    if spende.bestaetigt:
        raise BestaetigungsFehler("Für diese Sachspende gibt es schon eine Bestätigung.")
    if not spende.betrag:
        raise BestaetigungsFehler("Ohne Wert der Sachspende ist keine Bestätigung möglich.")
    b = Zuwendungsbestaetigung.objects.create(
        nummer=naechste_nummer(), art=Zuwendungsbestaetigung.Art.SACH, adresse=spende.adresse,
        ausgestellt_am=timezone.localdate(), betrag=spende.betrag, ausgestellt_von=von,
    )  # fmt: skip
    spende.bestaetigung = b
    spende.save(update_fields=["bestaetigung"])
    return b


@transaction.atomic
def stornieren(b: Zuwendungsbestaetigung, von: str) -> None:
    """Nummer bleibt vergeben; die Spenden lassen sich neu bestätigen (sie zeigen bis dahin
    noch auf die stornierte Bestätigung, damit deren PDF vollständig bleibt)."""
    if b.storniert_am:
        return
    b.storniert_am, b.storniert_von = timezone.now(), von
    b.save(update_fields=["storniert_am", "storniert_von"])


# --- PDF ---------------------------------------------------------------------------------------


def _beitrag(b) -> str:
    return f"{b:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _datum(d) -> str:
    return f"{d:%d.%m.%Y}" if d else "–"


def _koerperschaft(e, tafel) -> tuple[str, str]:
    return e.koerperschaft or tafel.name, e.anschrift or tafel.anschrift


def _grundlage(e) -> list[str]:
    zwecke = e.zwecke
    if e.grundlage == SpendenEinstellungen.Grundlage.FESTSTELLUNG:
        return [
            f"Die Einhaltung der satzungsmäßigen Voraussetzungen nach den §§ 51, 59, 60 und 61 AO "
            f"wurde vom Finanzamt {e.finanzamt}, StNr. {e.steuernummer} mit Bescheid vom "
            f"{_datum(e.bescheid_vom)} nach § 60a AO gesondert festgestellt. Wir fördern nach "
            f"unserer Satzung {zwecke}.",
        ]
    bescheid = ("dem Freistellungsbescheid" if e.grundlage == SpendenEinstellungen.Grundlage.
                FREISTELLUNG else "der Anlage zum Körperschaftsteuerbescheid")  # fmt: skip
    return [
        f"Wir sind wegen Förderung {zwecke} nach {bescheid} des Finanzamtes {e.finanzamt}, "
        f"StNr. {e.steuernummer} vom {_datum(e.bescheid_vom)} für den letzten "
        f"Veranlagungszeitraum {e.veranlagungszeitraum} nach § 5 Abs. 1 Nr. 9 des "
        "Körperschaftsteuergesetzes von der Körperschaftsteuer und nach § 3 Nr. 6 des "
        "Gewerbesteuergesetzes von der Gewerbesteuer befreit.",
    ]


def _seite(doc: Pdf, b: Zuwendungsbestaetigung, e, tafel) -> None:
    name, anschrift = _koerperschaft(e, tafel)
    spenden = list(b.spenden.order_by("datum", "pk"))
    if b.storniert_am:
        doc.ueberschrift(f"STORNIERT am {timezone.localtime(b.storniert_am):%d.%m.%Y} – "
                         "diese Bestätigung ist ungültig")  # fmt: skip
    doc.absatz(f"Aussteller (steuerbegünstigte Einrichtung): {name}, {anschrift}")
    if b.art == b.Art.SACH:
        doc.ueberschrift("Bestätigung über Sachzuwendungen")
    elif b.art == b.Art.SAMMEL:
        doc.ueberschrift("Sammelbestätigung über Geldzuwendungen/Mitgliedsbeiträge")
    else:
        doc.ueberschrift("Bestätigung über Geldzuwendungen/Mitgliedsbeitrag")
    doc.absatz(
        "im Sinne des § 10b des Einkommensteuergesetzes an eine der in § 5 Abs. 1 Nr. 9 des "
        "Körperschaftsteuergesetzes bezeichneten Körperschaften, Personenvereinigungen oder "
        f"Vermögensmassen. Nr. {b.nummer}", klein=True,
    )  # fmt: skip
    doc.angaben([("Name und Anschrift des Zuwendenden", ", ".join(b.adresse.anschrift_zeilen))])
    if b.art == b.Art.SAMMEL:
        zeitraum = f"{_datum(spenden[0].datum)} bis {_datum(spenden[-1].datum)}" if spenden else ""
        doc.angaben([
            ("Gesamtbetrag der Zuwendung in Ziffern", _beitrag(b.betrag)),
            ("in Buchstaben", euro(b.betrag)),
            ("Zeitraum der Sammelbestätigung", zeitraum),
        ])  # fmt: skip
    else:
        tag = _datum(spenden[0].datum) if spenden else ""
        doc.angaben([
            (("Wert" if b.art == b.Art.SACH else "Betrag") + " der Zuwendung in Ziffern",
             _beitrag(b.betrag)),
            ("in Buchstaben", euro(b.betrag)),
            ("Tag der Zuwendung", tag),
        ])  # fmt: skip
    if b.art == b.Art.SACH and spenden:
        s = spenden[0]
        doc.angaben([("Genaue Bezeichnung der Sachzuwendung mit Alter, Zustand, Kaufpreis usw.",
                      s.beschreibung)])  # fmt: skip
        herkunft = {
            Spende.Herkunft.BETRIEB: "Die Sachzuwendung stammt nach den Angaben des Zuwendenden "
            "aus dem Betriebsvermögen. Die Zuwendung wurde nach dem Wert der Entnahme (ggf. mit "
            "dem niedrigeren gemeinen Wert) und nach der Umsatzsteuer, die auf die Entnahme "
            "entfällt, bewertet.",
            Spende.Herkunft.PRIVAT: "Die Sachzuwendung stammt nach den Angaben des Zuwendenden "
            "aus dem Privatvermögen.",
            Spende.Herkunft.UNBEKANNT: "Der Zuwendende hat trotz Aufforderung keine Angaben zur "
            "Herkunft der Sachzuwendung gemacht.",
        }.get(s.herkunft)
        if herkunft:
            doc.absatz("[x] " + herkunft)
        if s.unterlagen:
            doc.absatz("[x] Geeignete Unterlagen, die zur Wertermittlung gedient haben, z. B. "
                       "Rechnung, Gutachten, liegen vor.")  # fmt: skip
    elif b.art == b.Art.GELD and spenden:
        verzicht = "Ja [x]  Nein [ ]" if spenden[0].verzicht_aufwand else "Ja [ ]  Nein [x]"
        doc.absatz(f"Es handelt sich um den Verzicht auf Erstattung von Aufwendungen: {verzicht}")
    doc.abstand()
    for satz in _grundlage(e):
        doc.absatz(satz)
    doc.absatz(f"Es wird bestätigt, dass die Zuwendung nur zur Förderung {e.zwecke} verwendet "
               "wird.")  # fmt: skip
    if b.art != b.Art.SACH and not e.mitgliedsbeitraege_abziehbar:
        doc.absatz("Es wird bestätigt, dass es sich nicht um einen Mitgliedsbeitrag handelt, "
                   "dessen Abzug nach § 10b Abs. 1 des Einkommensteuergesetzes ausgeschlossen "
                   "ist.")  # fmt: skip
    if b.art == b.Art.SAMMEL:
        doc.absatz("Es wird bestätigt, dass über die in der Gesamtsumme enthaltenen Zuwendungen "
                   "keine weiteren Bestätigungen, weder formelle Zuwendungsbestätigungen noch "
                   "Beitragsquittungen oder ähnliches ausgestellt wurden und werden. Ob es sich um "
                   "den Verzicht auf Erstattung von Aufwendungen handelt, ist der Anlage zur "
                   "Sammelbestätigung zu entnehmen.")  # fmt: skip
    doc.abstand()
    doc.absatz(f"{e.ort or tafel.ort}, {_datum(b.ausgestellt_am)}")
    doc.unterschriften([f"Unterschrift des Zuwendungsempfängers: {e.unterzeichnet_von}"])
    doc.abstand()
    doc.absatz(HAFTUNG, klein=True)
    if b.art == b.Art.SAMMEL:
        doc.element(PageBreak())
        doc.ueberschrift(f"Anlage zur Sammelbestätigung Nr. {b.nummer}")
        zeilen = [[_datum(s.datum),
                   "Mitgliedsbeitrag" if s.mitgliedsbeitrag else "Geldzuwendung",
                   "ja" if s.verzicht_aufwand else "nein", _beitrag(s.betrag)]
                  for s in spenden]  # fmt: skip
        zeilen.append(["Gesamtsumme", "", "", _beitrag(b.betrag)])
        doc.tabelle(["Datum der Zuwendung", "Art der Zuwendung",
                     "Verzicht auf die Erstattung von Aufwendungen (ja/nein)", "Betrag"],
                    zeilen, breiten=[0.2, 0.3, 0.3, 0.2], rechts=(3,), summe=True)  # fmt: skip


def pdf(bestaetigungen) -> bytes:
    e, tafel = SpendenEinstellungen.laden(), TafelEinstellungen.laden()
    doc = Pdf("Zuwendungsbestätigung")
    doc.inhalt = []  # kein großer Titel, jede Bestätigung hat ihre eigene Überschrift
    for nummer, b in enumerate(bestaetigungen):
        if nummer:
            doc.element(PageBreak())
        _seite(doc, b, e, tafel)
    return doc.erzeugen()
