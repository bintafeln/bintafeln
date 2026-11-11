from django.urls import path

from apps.uebernahme import views

app_name = "uebernahme"

urlpatterns = [
    path("", views.start, name="start"),
    path("besuche-konto/", views.besuche_konto, name="besuche_konto"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
