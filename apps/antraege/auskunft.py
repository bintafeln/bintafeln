"""Auskunft nach Art. 15 DSGVO zu einem Antrag (ADR 0021, 0024)."""

from django.utils import timezone

from apps.antraege import sprachen
from apps.antraege.models import AntragEinstellungen
from apps.core.pdf import Pdf


def _datum(wert) -> str:
    return f"{wert:%d.%m.%Y}" if wert else ""


def antrag_pdf(a) -> bytes:
    e = AntragEinstellungen.laden()
    doc = Pdf("Auskunft nach Art. 15 DSGVO", f"Gespeicherte Daten zum Antrag {a.nummer}")
    doc.ueberschrift("Antrag")
    doc.angaben(
        [
            ("Antragsnummer", a.nummer),
            ("Eingegangen am", f"{timezone.localtime(a.eingegangen_am):%d.%m.%Y %H:%M}"),
            ("Art", a.get_art_display()),
            ("Sprache", sprachen.sprache(a.sprache).deutsch),
            ("Status", a.get_status_display()),
            ("Kundennummer", a.kundennummer),
            ("Name", f"{a.anrede} {a.vorname} {a.nachname}".strip()),
            ("Geburtsdatum", _datum(a.geburtsdatum)),
            ("Anschrift", ", ".join(t for t in (a.strasse, f"{a.plz} {a.ort}".strip()) if t)),
            ("Telefon", a.telefon),
            ("E-Mail", a.email),
            ("Familienstand", a.familienstand),
            ("Staatsangehörigkeit", a.staatsangehoerigkeit),
            ("Bevorzugte Wochentage", a.wochentage),
            ("Bevorzugte Ausgabestelle", a.ausgabestelle),
            ("Nachricht", a.nachricht),
        ]
    )
    doc.ueberschrift("Weitere Personen im Haushalt")
    doc.tabelle(
        ["Vorname", "Nachname", "Geburtsdatum"],
        [[p.vorname, p.nachname, _datum(p.geburtsdatum)] for p in a.personen.all()],
    )
    doc.ueberschrift("Nachweise")
    doc.tabelle(["Datei", "Größe"], [[x.name, f"{x.groesse // 1024} KB"] for x in a.anhaenge.all()])
    doc.ueberschrift("Anmerkungen der Tafel")
    doc.tabelle(
        ["Datum", "Anmerkung", "Von"],
        [[f"{timezone.localtime(x.zeitpunkt):%d.%m.%Y}", x.text, x.von]
         for x in a.anmerkungen.all()],
        breiten=[0.15, 0.65, 0.2],
    )  # fmt: skip
    doc.ueberschrift("Hinweise")
    for satz in [
        "Zweck: Bearbeitung Ihres Antrags auf Berechtigung bei der Tafel "
        "(Art. 6 Abs. 1 lit. a und b DSGVO).",
        f"Speicherdauer: Abgeschlossene Anträge kommen nach {e.papierkorb_nach_tagen} Tagen in "
        f"den Papierkorb und werden {e.loeschen_nach_tagen} Tage danach gelöscht, samt "
        "Nachweisen.",
        "Ihre Rechte: Berichtigung, Löschung, Einschränkung der Verarbeitung, Widerruf der "
        "Einwilligung und Beschwerde bei einer Datenschutz-Aufsichtsbehörde.",
    ]:
        doc.absatz(satz)
        doc.abstand(1.5)
    return doc.erzeugen()
