from django.urls import path

from apps.serienbriefe import views

app_name = "serienbriefe"

urlpatterns = [
    path("", views.erstellen, name="erstellen"),
    path("vorlagen/", views.vorlagen, name="vorlagen"),
    path("vorlagen/neu/", views.vorlage, name="vorlage_neu"),
    path("vorlagen/<int:pk>/", views.vorlage, name="vorlage"),
    path("vorlagen/vorschau/", views.vorlage_vorschau, name="vorlage_vorschau"),
    path("vorlagen/vorschau/bild/", views.vorlage_bild, name="vorlage_bild"),
    path("vorlagen/<int:pk>/loeschen/", views.vorlage_loeschen, name="vorlage_loeschen"),
    path("grafiken/", views.grafiken_liste, name="grafiken"),
    path("grafiken/<int:pk>/", views.grafik, name="grafik"),
    path("grafiken/<int:pk>/loeschen/", views.grafik_loeschen, name="grafik_loeschen"),
]
