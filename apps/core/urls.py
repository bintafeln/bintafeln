from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.start, name="start"),
    path("einrichtung/", views.einrichtung, name="einrichtung"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("protokoll/", views.protokoll, name="protokoll"),
    path("healthz/", views.healthz, name="healthz"),
]
