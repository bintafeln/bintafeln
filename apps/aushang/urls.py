from django.urls import path

from apps.aushang import views

app_name = "aushang"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    # Der Monitor ohne Anmeldung, nur mit dem Schlüssel im Link
    path("zeigen/<str:schluessel>/", views.anzeige, name="anzeige"),
]
