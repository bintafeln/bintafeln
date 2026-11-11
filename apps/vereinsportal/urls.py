from django.urls import path

from apps.vereinsportal import views

app_name = "vereinsportal"

urlpatterns = [
    path("", views.start, name="start"),
    path("export/", views.export, name="export"),
    path("beleg/<int:pk>/", views.beleg, name="beleg"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
