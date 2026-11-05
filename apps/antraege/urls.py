from django.urls import path

from apps.antraege import views, views_aufnahme

app_name = "antraege"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("export/", views.export, name="export"),
    path("nachweise-importieren/", views.nachweise_importieren, name="nachweise_importieren"),
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
    path("<int:pk>/papierkorb/", views.papierkorb, name="papierkorb"),
    path("<int:pk>/auskunft/", views.auskunft_pdf, name="auskunft"),
    path("<int:pk>/nachweis/<int:anhang>/", views.anhang, name="anhang"),
    path("<int:pk>/nachweis-hinzufuegen/", views.nachweis_hinzufuegen, name="nachweis_hinzufuegen"),
    path(
        "<int:pk>/nachweis/<int:anhang>/entfernen/",
        views.nachweis_entfernen,
        name="nachweis_entfernen",
    ),  # fmt: skip
]
