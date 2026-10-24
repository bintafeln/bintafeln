"""Auskunft nach Art. 15 DSGVO zu einem Haushalt als PDF (ADR 0021).

Die Auskunft ist vollständig: Sie enthält auch Zusatzfelder der besonderen Kategorie und
abgeschaltete Felder, soweit Werte gespeichert sind. Wer sie erzeugt, steht im
Zugriffsprotokoll.
"""

from django.utils import timezone
from reportlab.lib.units import mm

from apps.ausgabe.konto import euro
from apps.core.pdf import Pdf
from apps.kunden.models import Haushalt, KundenEinstellungen, Notiz, Zugriff, Zusatzfeld


def _zusatz(felder, werte) -> list[tuple[str, str]]:
    paare = []
    for feld in felder:
        anzeige = feld.wert_anzeigen(werte.get(feld.schluessel))
        if anzeige:
            zusatz = " (besondere Kategorie, Art. 9 DSGVO)" if feld.besondere_kategorie else ""
            paare.append((feld.bezeichnung + zusatz, anzeige))
    return paare


def hat_besondere_kategorie(h: Haushalt) -> bool:
    felder = Zusatzfeld.objects.filter(besondere_kategorie=True)
    werte = [h.zusatz, *(p.zusatz for p in h.personen.all())]
    return any(f.wert_anzeigen(w.get(f.schluessel)) for f in felder for w in werte)


def _datum(wert) -> str:
    return f"{wert:%d.%m.%Y}" if wert else ""


def kunde_pdf(h: Haushalt) -> bytes:
    e = KundenEinstellungen.laden()
    felder = list(Zusatzfeld.objects.all())
    haushalt_felder = [f for f in felder if f.gilt_fuer == Zusatzfeld.GiltFuer.HAUSHALT]
    person_felder = [f for f in felder if f.gilt_fuer == Zusatzfeld.GiltFuer.PERSON]
    doc = Pdf("Auskunft nach Art. 15 DSGVO", f"Gespeicherte Daten zum Haushalt {h.kundennummer}")
    doc.absatz(
        "Diese Aufstellung enthält alle Angaben, die die Tafel zu diesem Haushalt und den "
        "zugehörigen Personen gespeichert hat. Rechtliche Hinweise stehen am Ende."
    )

    doc.ueberschrift("Haushalt")
    doc.angaben(
        [
            ("Kundennummer", h.kundennummer),
            ("Status", h.get_status_display()),
            ("Kundengruppe", h.kundengruppe.name if h.kundengruppe else ""),
            ("Kunde seit", _datum(h.kunde_seit)),
            ("Ausweis gültig bis", _datum(h.ausweis_gueltig_bis)),
            ("Letzter Besuch", _datum(h.letzter_besuch)),
            ("Einkommensart", h.einkommensart or ""),
            ("Anschrift", ", ".join(t for t in (h.strasse, f"{h.plz} {h.ort}".strip()) if t)),
            ("Telefon", h.telefon),
            ("E-Mail", h.email),
            ("Kontostand", euro(h.kontostand) if h.kontostand is not None else ""),
            ("Erwachsene laut Altsystem", h.anzahl_erwachsene),
            ("Kinder laut Altsystem", h.anzahl_kinder),
            *_zusatz(haushalt_felder, h.zusatz),
            ("Stand der Daten", f"Import vom {timezone.localtime(h.importiert_am):%d.%m.%Y}"),
        ]
    )

    doc.ueberschrift("Personen im Haushalt")
    for p in h.personen.all():
        doc.angaben(
            [
                ("Name", f"{p.anrede} {p.vorname} {p.nachname}".strip()),
                ("Rolle", "Hauptperson" if p.ist_hauptperson else "Angehörige"),
                ("Geburtsdatum", _datum(p.geburtsdatum)),
                ("Staatsangehörigkeit", p.staatsangehoerigkeit),
                ("Familienstand", p.familienstand),
                *_zusatz(person_felder, p.zusatz),
            ]
        )
        doc.abstand(3 * mm)

    doc.ueberschrift("Berechtigte Abholer")
    doc.tabelle(
        ["Name", "Geburtsdatum", "Eigene Kundennummer"],
        [[f"{a.vorname} {a.nachname}", _datum(a.geburtsdatum), a.eigene_kundennummer]
         for a in h.abholer.all()],
    )  # fmt: skip

    doc.ueberschrift("Sperren")
    doc.tabelle(
        ["Von", "Bis", "Begründung", "Eingetragen von"],
        [[_datum(s.von), _datum(s.bis), s.begruendung, s.eingetragen_von]
         for s in h.sperren.all()],
        breiten=[0.14, 0.14, 0.52, 0.2],
    )  # fmt: skip

    doc.ueberschrift("Anmerkungen")
    doc.tabelle(
        ["Datum", "Text", "Von"],
        [[_datum(b.datum), b.text, b.verfasst_von] for b in h.bemerkungen.all()],
        breiten=[0.14, 0.66, 0.2],
    )

    doc.ueberschrift("Notizen")
    doc.tabelle(
        ["Datum", "Text", "Von"],
        [[_datum(timezone.localtime(n.erstellt_am).date()), n.text, n.verfasst_von]
         for n in Notiz.objects.filter(kundennummer=h.kundennummer)],
        breiten=[0.14, 0.66, 0.2],
    )  # fmt: skip

    doc.ueberschrift("Ausnahmen")
    doc.tabelle(
        ["Datum", "Begründung", "Eingetragen von"],
        [[_datum(a.datum), a.begruendung, a.eingetragen_von] for a in h.ausnahmen.all()],
        breiten=[0.14, 0.66, 0.2],
    )

    doc.ueberschrift("Abholungen")
    doc.tabelle(
        ["Datum", "Uhrzeit", "Beitrag", "Ausgabestelle", "Eingetragen von"],
        [
            [
                _datum(a.datum),
                f"{a.uhrzeit:%H:%M}" if a.uhrzeit else "",
                euro(a.beitrag) if a.beitrag is not None else "",
                a.ausgabestelle.name if a.ausgabestelle else "",
                a.eingetragen_von,
            ]
            for a in h.abholungen.select_related("ausgabestelle")
        ],
        rechts=[2],
    )

    doc.ueberschrift("Kontobuchungen")
    doc.tabelle(
        ["Datum", "Art", "Belastung", "Gutschrift", "Anmerkung"],
        [
            [_datum(b.datum), b.get_art_display(), euro(b.soll), euro(b.haben), b.bemerkung]
            for b in h.buchungen.all()
        ],
        breiten=[0.14, 0.16, 0.15, 0.15, 0.4],
        rechts=[2, 3],
    )

    doc.ueberschrift("Wer die Daten aufgerufen hat")
    doc.tabelle(
        ["Zeitpunkt", "Mitarbeiterkonto"],
        [
            [f"{timezone.localtime(z.zeitpunkt):%d.%m.%Y %H:%M}", z.benutzername]
            for z in Zugriff.objects.filter(kundennummer=h.kundennummer)
        ],
        breiten=[0.3, 0.7],
    )

    doc.ueberschrift("Hinweise")
    for satz in hinweise(e):
        doc.absatz(satz)
        doc.abstand(1.5)
    return doc.erzeugen()


def hinweise(e: KundenEinstellungen) -> list[str]:
    return [
        "Zweck: Die Daten dienen der Prüfung der Berechtigung und der Ausgabe von "
        "Lebensmitteln (Art. 6 Abs. 1 lit. b DSGVO, bei Angaben der besonderen Kategorie "
        "Ihre Einwilligung nach Art. 9 Abs. 2 lit. a DSGVO).",
        "Herkunft: Die Angaben stammen aus Ihrer Anmeldung bei der Tafel.",
        "Empfänger: Die Daten werden nur von berechtigten Mitarbeitenden der Tafel genutzt und "
        "nicht an Dritte weitergegeben, soweit keine gesetzliche Pflicht besteht.",
        f"Speicherdauer: Abholungen und Ausnahmen werden nach {e.abholungen_aufbewahren_jahre} "
        f"Jahren gelöscht, das Zugriffsprotokoll nach {e.zugriffe_aufbewahren_tage} Tagen. Die "
        "übrigen Daten werden gelöscht, wenn Sie nicht mehr Kunde der Tafel sind.",
        "Ihre Rechte: Sie können die Berichtigung falscher Angaben, die Löschung oder die "
        "Einschränkung der Verarbeitung verlangen und eine Einwilligung jederzeit widerrufen. "
        "Sie können sich außerdem bei einer Datenschutz-Aufsichtsbehörde beschweren.",
    ]
