from apps.core.models import TafelEinstellungen
from apps.konten.rollen import ALLE, darf_mitarbeitende_verwalten, rollen_von
from apps.konten.zwei_faktor import ist_pflicht


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
    }
