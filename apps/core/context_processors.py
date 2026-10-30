from django.conf import settings

from apps.core import module
from apps.core.auswahl import NACHRICHT_ANLIEGEN_WAEHLBAR
from apps.core.menue import menue
from apps.core.models import TafelEinstellungen
from apps.konten.rollen import alle_rollen, darf_mitarbeitende_verwalten, rechte_von, rollen_von
from apps.konten.zwei_faktor import ist_pflicht
from bintafeln import programm
from bintafeln.version import version


def _darf_stempeln(benutzer) -> bool:
    # Spät eingebunden: Die App personal baut auf core auf, nicht umgekehrt.
    from apps.personal.arbeitszeit import darf_stempeln

    return darf_stempeln(benutzer)


def _ausgabestelle(request) -> dict:
    # Spät eingebunden: Die App ausgabe baut auf core auf, nicht umgekehrt.
    from apps.ausgabe.stelle import kontext

    return kontext(request)


def _impressum() -> str:
    """Link zum Impressum der Tafel, auch im App-Footer und auf der Anmeldeseite: interner Text
    (Tafel-Einstellungen) hat Vorrang, sonst der externe Link (ADR 0094)."""
    from apps.antraege.models import AntragEinstellungen

    return AntragEinstellungen.laden().rechtslink("impressum", "de")


def tafel(request):
    benutzer = getattr(request, "user", None)
    angemeldet = benutzer is not None and benutzer.is_authenticated
    rollen = rollen_von(benutzer) if angemeldet else set()
    offen = angemeldet and (
        (not benutzer.is_verified() and ist_pflicht(benutzer)) or benutzer.passwort_aendern
    )
    return {
        "menue": menue(request) if angemeldet and not offen else [],
        "tafel": TafelEinstellungen.laden(),
        "rollen": rollen,
        "rechte": rechte_von(benutzer) if angemeldet else frozenset(),
        # für die Anzeige in fester Reihenfolge
        "rollen_liste": [r.name for r in alle_rollen() if r.name in rollen] if angemeldet else [],
        # Solange die Pflicht-Einrichtung offen ist, zeigt das Menü nur "Abmelden".
        "zwei_faktor_offen": angemeldet and not benutzer.is_verified() and ist_pflicht(benutzer),
        "darf_mitarbeitende": angemeldet and darf_mitarbeitende_verwalten(benutzer),
        "passwort_offen": angemeldet and benutzer.passwort_aendern,
        "darf_stempeln": angemeldet and _darf_stempeln(benutzer),
        "demo": settings.DEMO,
        "heimnetz_https": settings.HEIMNETZ_ADRESSE,
        "version": version(),
        "programm": {"name": programm.NAME, "untertitel": programm.UNTERTITEL},
        "impressum_url": _impressum(),
        # Tablet einer Ausgabestelle: Seite lädt nach Ablauf neu, die Middleware meldet ab
        "stellen_konto_sekunden": 30 * 60 + 5 if angemeldet and benutzer.stelle_id else None,
        # Beiträge eingeschalteter Module zur Kopfzeile (z. B. Wetter), nur angemeldet
        "kopf_module": module.kopfzeile() if angemeldet and not offen else [],
        "seiten_module": module.seitenleiste() if angemeldet and not offen else [],
        "nachricht_anliegen": NACHRICHT_ANLIEGEN_WAEHLBAR,  # Fenster „Nachricht an die Verwaltung“
        # Ausgabestelle oben im Menü und Fortschritt des Tages in der Kopfzeile (ADR 0067)
        **(_ausgabestelle(request) if angemeldet and not offen else {}),
    }
