"""Ligaturen und unsichtbare Zeichen dürfen im Druck nicht als schwarzer Block erscheinen."""

import pytest

from apps.adressen.models import Adresse
from apps.core import zeichen
from apps.core.pdf import text


def test_bereinigen():
    assert zeichen.bereinigen("Pottho\ufb00s B\u00f6rde") == "Potthoffs B\u00f6rde"
    assert zeichen.bereinigen("\ufb01x \ufb02 \ufb03 \ufb04 \ufb05") == "fix fl ffi ffl st"
    assert zeichen.bereinigen("\u200b45131\u202fEssen\ufeff\u200e") == "45131 Essen"
    # gewöhnlicher Text bleibt, auch Umlaute, ß, Akzente und das geschützte Leerzeichen
    bleibt = "Stra\u00dfe 5, Caf\u00e9\u00a0M\u00fcller \u2013 \u20ac"
    assert zeichen.bereinigen(bleibt) == bleibt
    assert zeichen.bereinigen("") == "" and zeichen.bereinigen(None) is None


def test_pdf_text_druckt_keinen_block():
    assert text("Pottho\ufb00s\u200b <B\u00f6rde>") == "Potthoffs &lt;B\u00f6rde&gt;"
    assert text("") == "\u2013"


@pytest.mark.django_db
def test_adresse_speichert_bereinigt():
    a = Adresse.objects.create(
        art="person", vorname="Ste\ufb00i", nachname="Ho\ufb00mann\u200b",
        strasse="Pottho\ufb00s B\u00f6rde 1", plz="\u200b45136", ort="Essen\ufeff",
    )  # fmt: skip
    a.refresh_from_db()
    assert (a.vorname, a.nachname, a.strasse, a.plz, a.ort) == (
        "Steffi", "Hoffmann", "Potthoffs B\u00f6rde 1", "45136", "Essen")  # fmt: skip


@pytest.mark.django_db
def test_serienbrief_anschrift_und_platzhalter_ohne_block(pdf_text):
    from django.http import HttpResponse

    from apps.serienbriefe import brief, gestaltung

    assert "Potthoffs" in gestaltung.einsetzen("Hallo {ort}", {"ort": "Pottho\ufb00s"})
    inhalt = brief.briefe_pdf(
        [(["Erika Beispiel", "Pottho\ufb00s B\u00f6rde 1"], "Betreff", "Text")]
    )
    assert "Potthoffs" in pdf_text(HttpResponse(inhalt, "application/pdf"))
