from django.urls import path

from apps.core import (
    views,
    views_app,
    views_datensicherung,
    views_papierkorb,
    views_sicherung,
    views_speicher,
    views_update,
)

app_name = "core"

urlpatterns = [
    path("", views.start, name="start"),
    path("einrichtung/", views.einrichtung, name="einrichtung"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path(
        "einstellungen/hintergrund/<int:pk>/entfernen/",
        views.hintergrund_entfernen,
        name="hintergrund_entfernen",
    ),  # fmt: skip
    path("einstellungen/mail/", views.mail_einstellungen, name="mail_einstellungen"),
    path("einstellungen/speicher/", views_speicher.seite, name="speicher"),
    path("einstellungen/speicher/dateien/", views_speicher.dateien, name="dateien"),
    path("protokoll/", views.protokoll, name="protokoll"),
    path("papierkorb/", views_papierkorb.liste, name="papierkorb"),
    path("papierkorb/<int:pk>/", views_papierkorb.ansehen, name="papierkorb_eintrag"),
    path(
        "papierkorb/<int:pk>/wiederherstellen/",
        views_papierkorb.wiederherstellen,
        name="papierkorb_wiederherstellen",
    ),
    path(
        "papierkorb/<int:pk>/loeschen/",
        views_papierkorb.endgueltig_loeschen,
        name="papierkorb_loeschen",
    ),
    path("datensicherung/", views_datensicherung.seite, name="datensicherung"),
    path("datensicherung/export/", views_datensicherung.exportieren, name="daten_export"),
    path("datensicherung/pruefen/", views_datensicherung.pruefen, name="daten_pruefen"),
    path("datensicherung/vorschau/", views_datensicherung.vorschau, name="daten_vorschau"),
    path("datensicherung/uebernehmen/", views_datensicherung.uebernehmen, name="daten_uebernehmen"),
    path("datensicherung/verwerfen/", views_datensicherung.verwerfen, name="daten_verwerfen"),
    path("healthz/", views.healthz, name="healthz"),
    path("app/symbol-<int:groesse>.png", views_app.symbol, name="app_symbol"),
    path("app/manifest.webmanifest", views_app.manifest, name="manifest"),
    path("hilfe/", views.hilfe, name="hilfe"),
    path("suche/", views.suche, name="suche"),
    path("update/", views_update.seite, name="update"),
    path("update/starten/", views_update.starten, name="update_starten"),
    path("update/abrufen/", views_update.abrufen, name="update_abrufen"),
    path("update/spaeter/", views_update.spaeter, name="update_spaeter"),
    path("sicherungen/", views_sicherung.seite, name="sicherungen"),
    path("sicherungen/neu/", views_sicherung.auftrag, name="sicherungsauftrag_neu"),
    path("sicherungen/<int:pk>/", views_sicherung.auftrag, name="sicherungsauftrag"),
    path(
        "sicherungen/<int:pk>/loeschen/",
        views_sicherung.loeschen,
        name="sicherungsauftrag_loeschen",
    ),
    path("sicherungen/<int:pk>/jetzt/", views_sicherung.jetzt, name="sicherung_jetzt"),
]
