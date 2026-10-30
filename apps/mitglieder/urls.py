from django.urls import path

from apps.mitglieder import views

app_name = "mitglieder"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("spalten/", views.spalten, name="spalten"),
    path("neu/", views.bearbeiten, name="neu"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("<int:pk>/", views.mitglied, name="mitglied"),
    path("<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
