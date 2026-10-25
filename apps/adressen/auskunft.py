"""Auskunft nach Art. 15 DSGVO zu einer Adresse als PDF (ADR 0044)."""

from django.utils import timezone

from apps.core.pdf import Pdf


def _datum(wert) -> str:
    return f"{wert:%d.%m.%Y}" if wert else ""


def adresse_pdf(a) -> bytes:
    doc = Pdf("Auskunft nach Art. 15 DSGVO", f"Gespeicherte Daten zu {a.name}")
    doc.absatz(
        "Diese Aufstellung enthält alle Angaben, die die Tafel im Adressbuch zu Ihnen gespeichert "
        "hat. Sie dienen der Verwaltung von Spenden, Partnerschaften und Post an Sie."
    )
    doc.ueberschrift("Adresse")
    doc.angaben([
        ("Art", a.get_art_display()),
        ("Organisation", a.organisation),
        ("Ansprechperson", a.ansprechperson),
        ("Anrede", a.anrede),
        ("Vorname", a.vorname),
        ("Nachname", a.nachname),
        ("Straße und Hausnummer", a.strasse),
        ("PLZ und Ort", f"{a.plz} {a.ort}".strip()),
        ("Land", a.land),
        ("Telefon", a.telefon),
        ("Mobil", a.mobil),
        ("E-Mail", a.email),
        ("Webseite", a.webseite),
        ("Kategorien", ", ".join(k.name for k in a.kategorien.all())),
        ("Notiz", a.notiz),
    ])  # fmt: skip
    doc.ueberschrift("Einwilligungen")
    doc.angaben([
        ("Post seit", _datum(a.einwilligung_post)),
        ("E-Mail seit", _datum(a.einwilligung_email)),
        ("Name darf veröffentlicht werden seit", _datum(a.veroeffentlichen)),
    ])  # fmt: skip
    spenden = list(a.spenden.select_related("bestaetigung").order_by("datum"))
    if spenden:
        doc.ueberschrift("Spenden")
        doc.tabelle(["Datum", "Art", "Betrag/Wert", "Bezeichnung", "Bestätigung"], [
            [f"{s.datum:%d.%m.%Y}", s.get_art_display(),
             f"{s.betrag:.2f} €".replace(".", ",") if s.betrag else "",
             s.beschreibung or s.zweck, f"Nr. {s.bestaetigung.nummer}" if s.bestaetigt else ""]
            for s in spenden
        ], breiten=[0.15, 0.15, 0.17, 0.38, 0.15], rechts=(2,))  # fmt: skip
    bestaetigungen = list(a.bestaetigungen.order_by("nummer"))
    if bestaetigungen:
        doc.ueberschrift("Zuwendungsbestätigungen")
        doc.tabelle(["Nr.", "Art", "Ausgestellt am", "Betrag", "Status"], [
            [str(b.nummer), b.get_art_display(), f"{b.ausgestellt_am:%d.%m.%Y}",
             f"{b.betrag:.2f} €".replace(".", ","), "storniert" if b.storniert_am else "gültig"]
            for b in bestaetigungen
        ], breiten=[0.1, 0.35, 0.18, 0.17, 0.2], rechts=(3,))  # fmt: skip
    m = getattr(a, "mitglied", None)
    if m:
        doc.ueberschrift("Mitgliedschaft")
        doc.angaben([
            ("Mitgliedsnummer", m.nummer), ("Art", m.art), ("Eintritt", _datum(m.eintritt)),
            ("Austritt", _datum(m.austritt)), ("Grund des Austritts", m.austrittsgrund),
            ("Jahresbeitrag", f"{m.jahresbeitrag:.2f} €".replace(".", ",")),
            ("Zahlweise", m.zahlweise), ("Zahlungsart", m.zahlungsart), ("Notiz", m.notiz),
        ])  # fmt: skip
    from apps.serienbriefe.models import Versand

    versaende = Versand.objects.filter(empfaenger__contains=[f"a:{a.pk}"])
    if versaende:
        doc.ueberschrift("Serienbriefe")
        doc.tabelle(["Datum", "Art", "Betreff"], [
            [f"{timezone.localtime(v.am):%d.%m.%Y}", v.get_art_display(), v.betreff]
            for v in versaende
        ], breiten=[0.2, 0.2, 0.6])  # fmt: skip
    doc.ueberschrift("Verwaltung")
    doc.angaben([
        ("Angelegt am", f"{timezone.localtime(a.angelegt_am):%d.%m.%Y}"),
        ("Zuletzt geändert", f"{timezone.localtime(a.geaendert_am):%d.%m.%Y %H:%M}"
         if a.geaendert_am else ""),
        ("Erstellt am", f"{timezone.localtime():%d.%m.%Y %H:%M}"),
    ])  # fmt: skip
    return doc.erzeugen()
