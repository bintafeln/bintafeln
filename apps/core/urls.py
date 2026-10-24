from django.urls import path

from apps.core import views, views_datensicherung

app_name = "core"

urlpatterns = [
    path("", views.start, name="start"),
    path("einrichtung/", views.einrichtung, name="einrichtung"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("einstellungen/mail/", views.mail_einstellungen, name="mail_einstellungen"),
    path("protokoll/", views.protokoll, name="protokoll"),
    path("datensicherung/", views_datensicherung.seite, name="datensicherung"),
    path("datensicherung/export/", views_datensicherung.exportieren, name="daten_export"),
    path("datensicherung/pruefen/", views_datensicherung.pruefen, name="daten_pruefen"),
    path("datensicherung/vorschau/", views_datensicherung.vorschau, name="daten_vorschau"),
    path("datensicherung/uebernehmen/", views_datensicherung.uebernehmen, name="daten_uebernehmen"),
    path("datensicherung/verwerfen/", views_datensicherung.verwerfen, name="daten_verwerfen"),
    path("healthz/", views.healthz, name="healthz"),
]
