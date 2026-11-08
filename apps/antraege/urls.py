from django.urls import path

from apps.antraege import views, views_aufnahme

app_name = "antraege"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("export/", views.export, name="export"),
    path("nachweise-importieren/", views.nachweise_importieren, name="nachweise_importieren"),
    path("importieren/", views.antraege_importieren, name="antraege_importieren"),
    path("ausweise-pruefen/", views.ausweise_pruefen_alle, name="ausweise_pruefen_alle"),
    path(
        "ausweise-neu-pruefen/", views.ausweise_neu_pruefen_alle, name="ausweise_neu_pruefen_alle"
    ),
    path("ausweise-pruefen/stand/", views.ausweis_fortschritt, name="ausweis_fortschritt"),
    path("ausweispruefung/", views.ausweis_pruefung_liste, name="ausweis_pruefung_liste"),
    path(
        "ausweispruefung/sammel/",
        views.ausweis_sammel_entscheiden,
        name="ausweis_sammel_entscheiden",
    ),
    path("ausweispruefung/<int:pk>/", views.ausweis_entscheiden, name="ausweis_entscheiden"),
    path("ausweispruefung/<int:pk>/bild/", views.ausweis_miniatur, name="ausweis_miniatur"),
    path("spalten/", views.spalten, name="spalten"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("einstellungen/texte/<str:sprache>/", views.texte, name="texte"),
    path("einstellungen/uebersetzen/", views.uebersetzen, name="uebersetzen"),
    path(
        "einstellungen/uebersetzen/<str:sprache>/",
        views.uebersetzen_sprache,
        name="uebersetzen_sprache",
    ),
    path("<int:pk>/", views.antrag, name="antrag"),
    path("<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/aufnahme/", views_aufnahme.start, name="aufnahme"),
    path("<int:pk>/aufnahme/fertig/", views_aufnahme.fertig, name="aufnahme_fertig"),
    path("<int:pk>/aufnahme/<str:schritt>/", views_aufnahme.schritt, name="aufnahme_schritt"),
    path("<int:pk>/status/", views.status, name="status"),
    path("<int:pk>/anmerkung/", views.anmerkung, name="anmerkung"),
    path(
        "<int:pk>/anmerkung/<int:anmerkung>/",
        views.anmerkung_bearbeiten,
        name="anmerkung_bearbeiten",
    ),
    path("<int:pk>/papierkorb/", views.papierkorb, name="papierkorb"),
    path("<int:pk>/auskunft/", views.auskunft_pdf, name="auskunft"),
    path("<int:pk>/nachweis/<int:anhang>/", views.anhang, name="anhang"),
    path(
        "<int:pk>/nachweis/<int:anhang>/vorschau/",
        views.nachweis_vorschau,
        name="nachweis_vorschau",
    ),  # fmt: skip
    path("<int:pk>/nachweis-hinzufuegen/", views.nachweis_hinzufuegen, name="nachweis_hinzufuegen"),
    path(
        "<int:pk>/nachweis/<int:anhang>/ausweis/", views.nachweis_pruefen, name="nachweis_pruefen"
    ),  # fmt: skip
    path(
        "<int:pk>/ausweis/staat-uebernehmen/",
        views.nachweis_staat_uebernehmen,
        name="nachweis_staat_uebernehmen",
    ),  # fmt: skip
    path("<int:pk>/ausweis/bescheid/", views.ausweis_als_bescheid, name="ausweis_als_bescheid"),
    path("<int:pk>/ausweis/bereich/", views.ausweis_bereich_lesen, name="ausweis_bereich_lesen"),
    path(
        "<int:pk>/ausweis/neu-pruefen/",
        views.ausweis_neu_pruefen_einzeln,
        name="ausweis_neu_pruefen_einzeln",
    ),  # fmt: skip
    path(
        "<int:pk>/nachweis/<int:anhang>/entfernen/",
        views.nachweis_entfernen,
        name="nachweis_entfernen",
    ),  # fmt: skip
]
