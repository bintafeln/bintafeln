from django.urls import path

from apps.bexat import views

app_name = "bexat"

urlpatterns = [
    path("", views.start, name="start"),
    path("besuche-konto/", views.besuche_konto, name="besuche_konto"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
