import importlib


def test_betrieb_nutzt_dateinamen_mit_pruefsumme():
    """Sonst zeigt ein Browser nach einem Update bis zu einen Tag lang das alte Stylesheet."""
    betrieb = importlib.import_module("bintafeln.settings")
    assert betrieb.STORAGES["staticfiles"]["BACKEND"].endswith("ManifestStaticFilesStorage")
