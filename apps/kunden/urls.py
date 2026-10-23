from django.urls import path

from apps.kunden import views

app_name = "kunden"

urlpatterns = [
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("zusatzfelder/neu/", views.zusatzfeld_bearbeiten, name="zusatzfeld_neu"),
    path("zusatzfelder/<int:pk>/", views.zusatzfeld_bearbeiten, name="zusatzfeld"),
]
