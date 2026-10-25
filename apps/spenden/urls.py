from django.urls import path

from apps.spenden import views

app_name = "spenden"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("bestaetigungen/", views.bestaetigungen, name="bestaetigungen"),
    path("bestaetigungen/ausstellen/", views.ausstellen, name="ausstellen"),
    path("bestaetigungen/pdf/", views.pdf, name="pdf"),
    path("bestaetigungen/<int:nummer>/stornieren/", views.stornieren, name="stornieren"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
