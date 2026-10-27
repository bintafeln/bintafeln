from django.urls import path

from apps.ausgabe import views, views_korrekturen, views_sonderaktionen

app_name = "ausgabe"

urlpatterns = [
    path("", views.empfang, name="empfang"),
    path("ausgabestelle/", views.ausgabestelle_waehlen, name="ausgabestelle"),
    path("haushalt/<path:kundennummer>/abholung/", views.abholung_eintragen, name="eintragen"),
    path("haushalt/<path:kundennummer>/ausnahme/", views.ausnahme_erteilen, name="ausnahme"),
    path("abholung/<int:pk>/zuruecknehmen/", views.abholung_zuruecknehmen, name="zuruecknehmen"),
    path("haushalt/<path:kundennummer>/einzahlung/", views.einzahlung, name="einzahlung"),
    path("haushalt/<path:kundennummer>/korrektur/", views.korrektur, name="korrektur"),
    path("haushalt/<path:kundennummer>/notiz/", views.notiz, name="notiz"),
    path("notiz/<int:pk>/loeschen/", views.notiz_loeschen, name="notiz_loeschen"),
    path("haushalt/<path:kundennummer>/krank/", views.krank, name="krank"),
    path(
        "einzahlung/<int:pk>/zuruecknehmen/",
        views.einzahlung_zuruecknehmen,
        name="einzahlung_zuruecknehmen",
    ),
    path(
        "haushalt/<path:kundennummer>/sonderaktion/<int:aktion>/",
        views.sonderaktion_eintragen,
        name="sonderaktion_eintragen",
    ),
    path(
        "teilnahme/<int:pk>/zuruecknehmen/",
        views.teilnahme_zuruecknehmen,
        name="teilnahme_zuruecknehmen",
    ),
    path("sonderaktionen/", views_sonderaktionen.liste, name="sonderaktionen"),
    path("sonderaktionen/neu/", views_sonderaktionen.bearbeiten, name="sonderaktion_neu"),
    path("sonderaktionen/<int:pk>/", views_sonderaktionen.ansehen, name="sonderaktion"),
    path(
        "sonderaktionen/<int:pk>/bearbeiten/",
        views_sonderaktionen.bearbeiten,
        name="sonderaktion_bearbeiten",
    ),
    path(
        "sonderaktionen/<int:pk>/loeschen/",
        views_sonderaktionen.loeschen,
        name="sonderaktion_loeschen",
    ),
    path("korrektur/<str:art>/<int:pk>/", views.korrektur_beantragen, name="korrektur_beantragen"),
    path("korrekturen/", views_korrekturen.liste, name="korrekturen"),
    path(
        "korrekturen/<int:pk>/entscheiden/",
        views_korrekturen.entscheiden,
        name="korrektur_entscheiden",
    ),
    path("kasse/", views.kasse_ansehen, name="kasse"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
