from apps.core.models import TafelEinstellungen
from apps.konten.rollen import rollen_von
from apps.konten.zwei_faktor import ist_pflicht


def tafel(request):
    benutzer = getattr(request, "user", None)
    angemeldet = benutzer is not None and benutzer.is_authenticated
    return {
        "tafel": TafelEinstellungen.laden(),
        "rollen": rollen_von(benutzer) if angemeldet else set(),
        # Solange die Pflicht-Einrichtung offen ist, zeigt das Menü nur "Abmelden".
        "zwei_faktor_offen": angemeldet and not benutzer.is_verified() and ist_pflicht(benutzer),
    }
