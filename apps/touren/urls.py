from django.urls import path

from apps.touren import views

app_name = "touren"

urlpatterns = [
    path("stationen/", views.stationen, name="stationen"),
    path("stationen/neu/", views.bearbeiten, name="neu"),
    path("stationen/importieren/", views.importieren_ansicht, name="importieren"),
    path("stationen/ins-adressbuch/", views.alle_uebertragen, name="alle_uebertragen"),
    path("stationen/<int:pk>/", views.station, name="station"),
    path("stationen/<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("stationen/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("stationen/<int:pk>/ins-adressbuch/", views.uebertragen, name="uebertragen"),
]
