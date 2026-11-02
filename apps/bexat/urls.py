from django.urls import path

from apps.bexat import views

app_name = "bexat"

urlpatterns = [
    path("", views.start, name="start"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
