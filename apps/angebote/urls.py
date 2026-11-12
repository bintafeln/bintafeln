from django.urls import path

from apps.angebote import views

app_name = "angebote"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("<int:pk>/", views.angebot, name="angebot"),
    path("<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("<int:pk>/plaetze/", views.plaetze, name="plaetze"),
    path("<int:pk>/schliessen/", views.schliessen, name="schliessen"),
    path("<int:pk>/liste.pdf", views.liste_pdf, name="liste_pdf"),
    path("<int:pk>/liste.csv", views.liste_csv, name="liste_csv"),
    path("interesse/<int:pk>/stand/", views.stand, name="stand"),
    # am Einlass
    path("<int:pk>/eintragen/<str:kundennummer>/", views.eintragen, name="eintragen"),
    path("interesse/<int:pk>/austragen/", views.austragen, name="austragen"),
]
