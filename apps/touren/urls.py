from django.urls import path

from apps.touren import (
    views,
    views_fahrten,
    views_lieferscheine,
    views_statistik,
    views_touren,
)

app_name = "touren"

urlpatterns = [
    path("", views_touren.heute, name="heute"),
    path("tour/<int:pk>/", views_touren.fahren, name="fahren"),
    path("tour/<int:pk>/start/", views_touren.start, name="start"),
    path(
        "tour/<int:pk>/zuruecksetzen/",
        views_touren.tourtag_zuruecksetzen,
        name="tourtag_zuruecksetzen",
    ),
    path("tour/<int:pk>/zusatzstopp/", views_touren.zusatzstopp, name="zusatzstopp"),
    path("zusatzstopp/<int:pk>/entfernen/", views_touren.zusatzstopp_weg, name="zusatzstopp_weg"),
    path("neuer-stopp/", views_touren.heuler_stand, name="heuler"),
    path("neuer-stopp/<int:pk>/gesehen/", views_touren.heuler_gesehen, name="heuler_gesehen"),
    path("tour/<int:pk>/angefahren/<int:station_pk>/", views_touren.angefahren, name="angefahren"),
    path("tour/<int:pk>/beginnen/", views_fahrten.beginnen, name="fahrt_beginnen"),
    path("statistik/", views_statistik.uebersicht, name="statistik"),
    path("fahrzeug/neu/", views_fahrten.fahrzeug_neu, name="fahrzeug_neu"),
    path("fahrzeug/<int:pk>/", views_fahrten.fahrzeug, name="fahrzeug"),
    path("fahrzeug/papier/<int:pk>/", views_fahrten.papier, name="fahrzeug_papier"),
    path(
        "fahrzeug/papier/<int:pk>/entfernen/", views_fahrten.papier_weg, name="fahrzeug_papier_weg"
    ),
    path("fahrten/", views_fahrten.liste, name="fahrten"),
    path("fahrten/meldungen/", views_fahrten.meldungen_liste, name="meldungen"),
    path("fahrten/meldungen/<int:pk>/", views_fahrten.meldung_erledigen, name="meldung_erledigen"),
    path("fahrten/<int:pk>/melden/", views_fahrten.melden, name="fahrt_melden"),
    path("fahrten/<int:pk>/", views_fahrten.bearbeiten, name="fahrt"),
    path("fahrten/<int:pk>/loeschen/", views_fahrten.fahrt_loeschen, name="fahrt_loeschen"),
    path("fahrten/<int:pk>/beenden/", views_fahrten.beenden, name="fahrt_beenden"),
    path("planen/", views_touren.touren, name="touren"),
    path("planen/neu/", views_touren.tour_neu, name="tour_neu"),
    path("planen/stationen-suche/", views_touren.stationen_suche, name="stationen_suche"),
    path("planen/karte/", views_touren.karte, name="karte"),
    path("planen/importieren/", views_touren.touren_importieren, name="touren_importieren"),
    path("planen/<int:pk>/", views_touren.tour, name="tour"),
    path("planen/<int:pk>/loeschen/", views_touren.tour_loeschen, name="tour_loeschen"),
    path("planen/<int:pk>/besetzung/", views_touren.besetzung_aendern, name="besetzung"),
    path("planen/<int:pk>/senden/", views_touren.tour_senden, name="tour_senden"),
    path("planen/<int:pk>/halt/", views_touren.halt_neu, name="halt_neu"),
    path("planen/halt/<int:pk>/", views_touren.halt_aendern, name="halt_aendern"),
    path("einstellungen/", views_lieferscheine.einstellungen, name="einstellungen"),
    path("einrichten/", views_lieferscheine.einrichten, name="einrichten"),
    path("lieferscheine/", views_lieferscheine.liste, name="lieferscheine"),
    path("lieferscheine/<int:pk>.pdf", views_lieferscheine.pdf, name="lieferschein_pdf"),
    path(
        "lieferscheine/<int:pk>/senden/", views_lieferscheine.nachsenden, name="lieferschein_senden"
    ),
    path(
        "lieferscheine/<int:pk>/loeschen/",
        views_lieferscheine.loeschen,
        name="lieferschein_loeschen",
    ),
    path("stationen/<int:pk>/lieferschein/", views_lieferscheine.ausfuellen, name="lieferschein"),
    path("stationen/", views.stationen, name="stationen"),
    path("stationen/neu/", views.bearbeiten, name="neu"),
    path("stationen/importieren/", views.importieren_ansicht, name="importieren"),
    path("stationen/ins-adressbuch/", views.alle_uebertragen, name="alle_uebertragen"),
    path("stationen/<int:pk>/", views.station, name="station"),
    path("stationen/<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("stationen/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("stationen/<int:pk>/ins-adressbuch/", views.uebertragen, name="uebertragen"),
]
