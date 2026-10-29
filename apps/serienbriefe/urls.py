from django.urls import path

from apps.serienbriefe import views

app_name = "serienbriefe"

urlpatterns = [
    path("", views.erstellen, name="erstellen"),
    path("vorlagen/", views.vorlagen, name="vorlagen"),
    path("vorlagen/neu/", views.vorlage, name="vorlage_neu"),
    path("vorlagen/<int:pk>/", views.vorlage, name="vorlage"),
    path("vorlagen/vorschau/", views.vorlage_vorschau, name="vorlage_vorschau"),
    path("vorlagen/<int:pk>/loeschen/", views.vorlage_loeschen, name="vorlage_loeschen"),
]
