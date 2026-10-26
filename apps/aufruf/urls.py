from django.urls import path

from apps.aufruf import views, views_anzeige, views_einstellungen

app_name = "aufruf"

urlpatterns = [
    path("", views.start, name="start"),
    path("leiste/", views.leiste, name="leiste"),
    path("<int:pk>/", views.steuerung, name="steuerung"),
    path("<int:pk>/mobil/", views.mobil, name="mobil"),
    path("<int:pk>/verschieben/<str:nummer>/", views.verschieben, name="verschieben"),
    path("<int:pk>/starten/", views.starten, name="starten"),
    path("<int:pk>/weiter/", views.weiter, name="weiter"),
    path("<int:pk>/zurueck/", views.zurueck, name="zurueck"),
    path("<int:pk>/neustart/", views.neustart, name="neustart"),
    path("<int:pk>/reihenfolge.csv", views.liste, name="liste"),
    path("<int:pk>/api/stand/", views.api_stand, name="api_stand"),
    path("<int:pk>/api/status/", views.api_status, name="api_status"),
    path("<int:pk>/api/starten/", views.api_starten, name="api_starten"),
    path("<int:pk>/api/weiter/", views.api_weiter, name="api_weiter"),
    path("<int:pk>/api/zurueck/", views.api_zurueck, name="api_zurueck"),
    path("<int:pk>/api/abfrage/", views.api_abfrage, name="api_abfrage"),
    path("<int:pk>/api/spaetzuender/", views.api_spaetzuender, name="api_spaetzuender"),
    # Einstellungen
    path("einstellungen/", views_einstellungen.einstellungen, name="einstellungen"),
    path("einstellungen/<int:pk>/", views_einstellungen.stelle, name="einstellungen_stelle"),
    path("einstellungen/<int:pk>/schluessel/", views_einstellungen.schluessel_neu,
         name="schluessel_neu"),
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
]  # fmt: skip
