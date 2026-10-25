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
    doc.ueberschrift("Verwaltung")
    doc.angaben([
        ("Angelegt am", f"{timezone.localtime(a.angelegt_am):%d.%m.%Y}"),
        ("Zuletzt geändert", f"{timezone.localtime(a.geaendert_am):%d.%m.%Y %H:%M}"
         if a.geaendert_am else ""),
        ("Erstellt am", f"{timezone.localtime():%d.%m.%Y %H:%M}"),
    ])  # fmt: skip
    return doc.erzeugen()
