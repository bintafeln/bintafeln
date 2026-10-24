from django.conf import settings

from apps.core.models import TafelEinstellungen
from apps.konten.rollen import ALLE, darf_mitarbeitende_verwalten, rollen_von
from apps.konten.zwei_faktor import ist_pflicht
from bintafeln.version import version


def _darf_stempeln(benutzer) -> bool:
    # Spät eingebunden: Die App personal baut auf core auf, nicht umgekehrt.
    from apps.personal.arbeitszeit import darf_stempeln

    return darf_stempeln(benutzer)


def tafel(request):
    benutzer = getattr(request, "user", None)
    angemeldet = benutzer is not None and benutzer.is_authenticated
    rollen = rollen_von(benutzer) if angemeldet else set()
    return {
        "tafel": TafelEinstellungen.laden(),
        "rollen": rollen,
        # für die Anzeige in fester Reihenfolge
        "rollen_liste": [rolle for rolle in ALLE if rolle in rollen],
        # Solange die Pflicht-Einrichtung offen ist, zeigt das Menü nur "Abmelden".
        "zwei_faktor_offen": angemeldet and not benutzer.is_verified() and ist_pflicht(benutzer),
        "darf_mitarbeitende": angemeldet and darf_mitarbeitende_verwalten(benutzer),
        "passwort_offen": angemeldet and benutzer.passwort_aendern,
        "darf_stempeln": angemeldet and _darf_stempeln(benutzer),
        "demo": settings.DEMO,
        "version": version(),
    }
