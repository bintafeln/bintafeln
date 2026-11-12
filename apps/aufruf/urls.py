from django.urls import path

from apps.aufruf import views, views_anzeige, views_einstellungen

app_name = "aufruf"

urlpatterns = [
    path("", views.start, name="start"),
    path("leiste/", views.leiste, name="leiste"),
    path("handys/<str:nummer>/zuruecksetzen/", views.handys_zuruecksetzen,
         name="handys_zuruecksetzen"),  # fmt: skip
    # Einstellungen
    path("einstellungen/", views_einstellungen.einstellungen, name="einstellungen"),
    path("einstellungen/<int:pk>/", views_einstellungen.stelle, name="einstellungen_stelle"),
    path("einstellungen/<int:pk>/schluessel/", views_einstellungen.schluessel_neu,
         name="schluessel_neu"),
    path("einstellungen/aushang.pdf", views_einstellungen.aushang, name="aushang"),
    path("einstellungen/info/neu/", views_einstellungen.info, name="info_neu"),
    path("einstellungen/info/<int:pk>/", views_einstellungen.info, name="info"),
    path("einstellungen/info/<int:pk>/loeschen/", views_einstellungen.info_loeschen,
         name="info_loeschen"),
    # Anzeige-Geräte ohne Anmeldung, nur mit Schlüssel
    path("anzeige/<str:schluessel>/", views_anzeige.anzeige, name="anzeige"),
    path("anzeige/<str:schluessel>/monitor/", views_anzeige.monitor, name="monitor"),
    path("anzeige/<str:schluessel>/abfrage/", views_anzeige.abfrage, name="abfrage"),
    path("anzeige/<str:schluessel>/kiosk/", views_anzeige.kiosk, name="kiosk"),
    path("anzeige/<str:schluessel>/stand/", views_anzeige.stand, name="anzeige_stand"),
    path("anzeige/<str:schluessel>/abfrage/api/", views_anzeige.abfrage_api,
         name="anzeige_abfrage"),
    path("anzeige/<str:schluessel>/layout/", views_anzeige.layout, name="anzeige_layout"),
    path("anzeige/<str:schluessel>/info/<int:pk>/", views_anzeige.datei, name="anzeige_datei"),
    # Steuerung (angemeldet, mit Recht): der Schlüssel der Ausgabestelle statt ihrer Nummer, damit
    # sich die Adressen nicht erraten lassen. Steht am Ende, weil <str:…> sonst die festen
    # Adressen oben (einstellungen/, anzeige/ …) abfangen würde.
    path("<str:kennung>/", views.steuerung, name="steuerung"),
    path("<str:kennung>/mobil/", views.mobil, name="mobil"),
    path("<str:kennung>/verschieben/<str:nummer>/", views.verschieben, name="verschieben"),
    path("<str:kennung>/starten/", views.starten, name="starten"),
    path("<str:kennung>/weiter/", views.weiter, name="weiter"),
    path("<str:kennung>/zurueck/", views.zurueck, name="zurueck"),
    path("<str:kennung>/neustart/", views.neustart, name="neustart"),
    path("<str:kennung>/reihenfolge.csv", views.liste, name="liste"),
    path("<str:kennung>/api/stand/", views.api_stand, name="api_stand"),
    path("<str:kennung>/api/status/", views.api_status, name="api_status"),
    path("<str:kennung>/api/starten/", views.api_starten, name="api_starten"),
    path("<str:kennung>/api/weiter/", views.api_weiter, name="api_weiter"),
    path("<str:kennung>/api/zurueck/", views.api_zurueck, name="api_zurueck"),
    path("<str:kennung>/api/fortsetzen/", views.api_fortsetzen, name="api_fortsetzen"),
    path("<str:kennung>/api/abfrage/", views.api_abfrage, name="api_abfrage"),
    path("<str:kennung>/api/spaetzuender/", views.api_spaetzuender, name="api_spaetzuender"),
]  # fmt: skip
