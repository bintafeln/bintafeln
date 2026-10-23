from types import SimpleNamespace

from apps.core.models import TafelEinstellungen
from apps.core.templatetags.protokoll import aenderungen
from apps.konten.models import Benutzer


def eintrag(modell, roh, anzeige):
    return SimpleNamespace(
        content_type=SimpleNamespace(model_class=lambda: modell),
        changes_dict=roh,
        changes_display_dict=anzeige,
    )


def test_normale_aenderung():
    e = eintrag(TafelEinstellungen, {"name": ["Alt", "Neu"]}, {"Name der Tafel": ["Alt", "Neu"]})
    assert aenderungen(e) == [("Name der Tafel", "Alt → Neu")]


def test_m2m_aenderung():
    roh = {"groups": {"type": "m2m", "operation": "add", "objects": ["Admin", "Büro"]}}
    e = eintrag(Benutzer, roh, {"Gruppen": ["type", "objects", "operation"]})
    assert aenderungen(e) == [("Gruppen", "hinzugefügt: Admin, Büro")]


def test_m2m_unbekannte_operation():
    roh = {"groups": {"type": "m2m", "operation": "neu"}}
    assert aenderungen(eintrag(Benutzer, roh, {})) == [("Gruppen", "neu: ")]


def test_entferntes_feld_und_geloeschtes_modell():
    # Feld gibt es nicht mehr: Rohname und Rohwerte
    e = eintrag(TafelEinstellungen, {"alt_feld": ["a", "b"]}, {})
    assert aenderungen(e) == [("alt_feld", "a → b")]
    # Modellklasse existiert nicht mehr (model_class() liefert None)
    e = eintrag(None, {"name": ["a", "b"]}, {"name": ["a", "b"]})
    assert aenderungen(e) == [("name", "a → b")]
