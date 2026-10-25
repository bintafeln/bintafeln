"""Auskunft nach Art. 15 DSGVO zu Mitarbeitenden als PDF (ADR 0021).

Vollständig, also auch mit den Personaldaten (Verträge, Abwesenheiten, Stunden, Arbeitszeiten).
Abrufen dürfen sie deshalb nur Admin, die Rolle Personal und die Person selbst.
"""

import datetime as dt
from decimal import Decimal

from django.utils import timezone

from apps.core.pdf import Pdf
from apps.konten import rollen, zwei_faktor
from apps.konten.models import PersonalEinstellungen, Stammdaten


def _wert(wert) -> str:
    if wert is None or wert == "":
        return ""
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, dt.datetime):
        return f"{timezone.localtime(wert):%d.%m.%Y %H:%M}"
    if isinstance(wert, dt.date):
        return f"{wert:%d.%m.%Y}"
    if isinstance(wert, Decimal):
        return f"{wert.normalize():f}".replace(".", ",")
    return str(wert)


def mitarbeiter_pdf(b) -> bytes:
    doc = Pdf("Auskunft nach Art. 15 DSGVO", f"Gespeicherte Daten zu {b.get_full_name() or b}")
    doc.absatz(
        "Diese Aufstellung enthält alle Angaben, die die Tafel zu Ihrem Konto und Ihrer "
        "Mitarbeit gespeichert hat. Hochgeladene Dokumente sind nur mit Titel aufgeführt; "
        "eine Kopie erhalten Sie auf Wunsch."
    )

    doc.ueberschrift("Konto")
    doc.angaben(
        [
            ("Benutzername", b.username),
            ("Name", b.get_full_name()),
            ("E-Mail", b.email),
            (
                "Rollen",
                ", ".join(r.name for r in rollen.alle_rollen() if r.name in rollen.rollen_von(b)),
            ),
            ("Beschäftigung", b.get_beschaeftigung_display()),
            ("Konto angelegt am", _wert(b.date_joined)),
            ("Zuletzt angemeldet am", _wert(b.last_login)),
            ("Zwei-Faktor-Anmeldung eingerichtet", _wert(zwei_faktor.app_geraet(b) is not None)),
            ("Gesperrt am", _wert(b.gesperrt_am)),
        ]
    )

    geraete = b.vertraute_geraete.all()
    if geraete:
        doc.ueberschrift("Vertraute Geräte (Anmeldung ohne Zwei-Faktor-Code)")
        doc.tabelle(["Gerät", "Vertraut seit", "Gültig bis", "Zuletzt benutzt"],
                    [[g.bezeichnung, _wert(g.angelegt_am), _wert(g.gueltig_bis),
                      _wert(g.zuletzt_am)] for g in geraete])  # fmt: skip

    m = getattr(b, "mitglied", None)
    if m:
        doc.ueberschrift("Mitgliedschaft im Verein")
        doc.angaben([("Mitgliedsnummer", m.nummer), ("Art", m.art),
                     ("Eintritt", _wert(m.eintritt)), ("Austritt", _wert(m.austritt))])  # fmt: skip
        doc.absatz("Alle Angaben zur Mitgliedschaft und zu Beiträgen enthält die Auskunft aus "
                   "dem Adressbuch.", klein=True)  # fmt: skip

    kontakte = b.ausgabestellen_kontakte.select_related("ausgabestelle")
    if kontakte:
        doc.ueberschrift("Ansprechpartner für Ausgabestellen")
        doc.tabelle(["Ausgabestelle", "Zuständigkeit", "Telefon", "E-Mail"],
                    [[k.ausgabestelle.name, k.zustaendigkeit, k.telefon, k.email]
                     for k in kontakte])  # fmt: skip

    doc.ueberschrift("Stammdaten")
    s = Stammdaten.objects.filter(benutzer=b).first()
    if s is None:
        doc.absatz("Keine Stammdaten gespeichert.")
    else:
        ohne = {"id", "benutzer", "fs_kopie_datei", "fs_kopie_typ"}
        doc.angaben(
            [
                (f.verbose_name, _wert(getattr(s, f.name)))
                for f in Stammdaten._meta.fields
                if f.name not in ohne and getattr(s, f.name) not in (None, "")
            ]
        )
        if s.fs_kopie_datei:
            doc.absatz("Eine Kopie des Führerscheins ist verschlüsselt gespeichert.", klein=True)

    doc.ueberschrift("Schulungen und Belehrungen")
    doc.tabelle(
        ["Thema", "Datum", "Gültig bis", "Anmerkung"],
        [[x.thema, _wert(x.datum), _wert(x.gueltig_bis), x.bemerkung] for x in b.schulungen.all()],
    )

    doc.ueberschrift("Dokumente")
    doc.tabelle(
        ["Titel", "Kategorie", "Dokumentdatum", "Hochgeladen"],
        [
            [d.titel, d.kategorie, _wert(d.datum), f"{_wert(d.hochgeladen_am)} {d.hochgeladen_von}"]
            for d in b.dokumente.select_related("kategorie")
        ],
    )

    doc.ueberschrift("Arbeitsverträge")
    doc.tabelle(
        ["Beginn", "Ende", "Tätigkeit", "Std./Woche", "Urlaub/Jahr", "Stundenlohn"],
        [
            [_wert(v.beginn), _wert(v.ende) or "unbefristet", v.taetigkeit, _wert(v.wochenstunden),
             _wert(v.urlaubstage), _wert(v.stundenlohn)]
            for v in b.vertraege.all()
        ],
    )  # fmt: skip

    doc.ueberschrift("Urlaub und Krankheit")
    doc.tabelle(
        ["Art", "Von", "Bis", "Tage", "Bescheinigung", "Anmerkung"],
        [
            [a.get_art_display(), _wert(a.von), _wert(a.bis), _wert(a.tage),
             _wert(a.au_vorgelegt) if a.art == "krank" else "", a.bemerkung]
            for a in b.abwesenheiten.all()
        ],
    )  # fmt: skip
    abweichend = [[u.jahr, _wert(u.anspruch), _wert(u.verfall_am)] for u in b.urlaubsjahre.all()]
    if abweichend:
        doc.abstand()
        doc.tabelle(["Urlaubsjahr", "Abweichender Anspruch", "Verfall am"], abweichend)

    doc.ueberschrift("Nachgetragene Stunden")
    doc.tabelle(
        ["Datum", "Stunden", "Anmerkung"],
        [[_wert(x.datum), _wert(x.stunden), x.bemerkung] for x in b.stunden.all()],
    )

    doc.ueberschrift("Arbeitszeiten (gestempelt)")
    doc.tabelle(
        ["Kommen", "Gehen", "Anmerkung", "Korrigiert von"],
        [
            [_wert(z.beginn), _wert(z.ende) or "offen", z.bemerkung, z.korrigiert_von]
            for z in b.zeitbuchungen.order_by("beginn")
        ],
    )

    jahre = PersonalEinstellungen.laden().stammdaten_loeschen_jahre
    doc.ueberschrift("Hinweise")
    for satz in [
        "Zweck: Organisation der Mitarbeit bei der Tafel, bei Beschäftigten die Durchführung "
        "des Arbeitsverhältnisses (Art. 6 Abs. 1 lit. b und c DSGVO, § 26 BDSG).",
        "Empfänger: Die Daten nutzen nur berechtigte Personen der Tafel. Weitergabe nur, wo ein "
        "Gesetz es verlangt (z. B. Lohnabrechnung, Sozialversicherung, Finanzamt).",
        f"Speicherdauer: Nach dem Ende der Mitarbeit wird das Konto gesperrt; persönliche "
        f"Angaben und Personaldaten werden {jahre} Jahre danach automatisch gelöscht.",
        "Ihre Rechte: Berichtigung, Löschung, Einschränkung der Verarbeitung, Widerspruch und "
        "Beschwerde bei einer Datenschutz-Aufsichtsbehörde.",
    ]:
        doc.absatz(satz)
        doc.abstand(1.5)
    return doc.erzeugen()
