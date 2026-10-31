from django.urls import path

from apps.warteliste import views

app_name = "warteliste"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("export/", views.export, name="export"),
    path("einladen/", views.einladen, name="einladen"),
    path("status/", views.status_mehrere, name="status"),
    path("antrag/<int:pk>/", views.eintrag, name="eintrag"),
    path("termine/", views.termine, name="termine"),
    path("termine/neu/", views.termin_bearbeiten, name="termin_neu"),
    path("termine/<int:pk>/", views.termin, name="termin"),
    path("termine/<int:pk>/bearbeiten/", views.termin_bearbeiten, name="termin_bearbeiten"),
    path("termine/<int:pk>/absagen/", views.termin_absagen, name="termin_absagen"),
    path("termine/<int:pk>/loeschen/", views.termin_loeschen, name="termin_loeschen"),
    path("termine/<int:pk>/druckliste.pdf", views.druckliste, name="druckliste"),
    path("abgleich/", views.abgleich, name="abgleich"),
    path("abgleich/entscheiden/", views.abgleich_entscheiden, name="abgleich_entscheiden"),
    path("dubletten/", views.dubletten, name="dubletten"),
    path("dubletten/entscheiden/", views.dublette, name="dublette"),
    path("streichungsliste/", views.streichungsliste, name="streichungsliste"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("einstellungen/texte/", views.texte, name="texte"),
    path("einstellungen/texte/uebersetzen/", views.uebersetzen, name="uebersetzen"),
    path(
        "einstellungen/texte/uebersetzen/<str:sprache>/",
        views.uebersetzen_sprache,
        name="uebersetzen_sprache",
    ),  # fmt: skip
    path("einstellungen/texte/<str:sprache>/", views.texte_sprache, name="texte_sprache"),
]
