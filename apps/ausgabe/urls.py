from django.urls import path

from apps.ausgabe import views

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
    path(
        "einzahlung/<int:pk>/zuruecknehmen/",
        views.einzahlung_zuruecknehmen,
        name="einzahlung_zuruecknehmen",
    ),
    path("kasse/", views.kasse_ansehen, name="kasse"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
