from django.urls import path

from apps.adressen import views

app_name = "adressen"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("spalten/", views.spalten, name="spalten"),
    path("neu/", views.bearbeiten, name="neu"),
    path("importieren/", views.importieren_ansicht, name="importieren"),
    path("<int:pk>/", views.adresse, name="adresse"),
    path("<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("<int:pk>/konto-sperren/", views.konto_sperren, name="konto_sperren"),
    path("<int:pk>/konto-entsperren/", views.konto_entsperren, name="konto_entsperren"),
    path("<int:pk>/auskunft/", views.auskunft, name="auskunft"),
]
