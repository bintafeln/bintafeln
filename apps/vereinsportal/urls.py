from django.urls import path

from apps.vereinsportal import views

app_name = "vereinsportal"

urlpatterns = [
    path("", views.start, name="start"),
    path("abruf/", views.abruf, name="abruf"),
    path("abruf/stand/", views.abruf_stand, name="abruf_stand"),
    path("abruf/zugang/", views.zugang, name="zugang"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
