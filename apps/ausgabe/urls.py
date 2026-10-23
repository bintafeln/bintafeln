from django.urls import path

from apps.ausgabe import views

app_name = "ausgabe"

urlpatterns = [
    path("", views.empfang, name="empfang"),
    path("ausgabestelle/", views.ausgabestelle_waehlen, name="ausgabestelle"),
    path("haushalt/<path:kundennummer>/abholung/", views.abholung_eintragen, name="eintragen"),
    path("haushalt/<path:kundennummer>/ausnahme/", views.ausnahme_erteilen, name="ausnahme"),
    path("abholung/<int:pk>/zuruecknehmen/", views.abholung_zuruecknehmen, name="zuruecknehmen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
