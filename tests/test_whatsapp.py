"""WhatsApp „Klick zum Chat“ (ADR 0098). Alle Nummern sind erfunden."""

import pytest

from apps.core import whatsapp


def test_nummer_bereinigen():
    # Führende 0 → Ländervorwahl; bereits internationale Nummern bleiben
    assert whatsapp.nummer_bereinigen("0171 123 4567") == "491711234567"
    assert whatsapp.nummer_bereinigen("+49 171 1234567") == "491711234567"
    assert whatsapp.nummer_bereinigen("0049 (171) 1234567") == "491711234567"
    assert whatsapp.nummer_bereinigen("0664 1234", vorwahl="43") == "436641234"
    assert whatsapp.nummer_bereinigen("") == ""
    assert whatsapp.nummer_bereinigen("kein Anschluss") == ""


def test_link():
    assert whatsapp.link("0171 1234567") == "https://wa.me/491711234567"
    mit_text = whatsapp.link("0171 1234567", "Hallo Max & Co?")
    assert mit_text == "https://wa.me/491711234567?text=Hallo%20Max%20%26%20Co%3F"
    assert whatsapp.link("") == ""  # keine Nummer → kein Link


@pytest.mark.django_db
def test_fuer_person_nutzt_vorwahl_der_tafel():
    from apps.adressen.models import Adresse
    from apps.core.models import TafelEinstellungen

    e = TafelEinstellungen.laden()
    e.laendervorwahl = "43"  # Österreich
    e.save()
    person = Adresse(art=Adresse.Art.PERSON, nachname="Muster", mobil="0664 1234")
    assert whatsapp.fuer_person(person, "Hallo") == "https://wa.me/436641234?text=Hallo"
    # Ohne Handynummer oder ohne Person kein Link
    assert whatsapp.fuer_person(Adresse(art=Adresse.Art.PERSON, nachname="X")) == ""
    assert whatsapp.fuer_person(None) == ""
