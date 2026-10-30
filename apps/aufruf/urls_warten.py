"""Wartezeit aufs Handy (ADR 0090): öffentlich, ohne Anmeldung bei bintafeln."""

from django.urls import path

from apps.aufruf import views_warten

app_name = "warten"

urlpatterns = [
    path("", views_warten.seite, name="seite"),
    path("abmelden/", views_warten.abmelden, name="abmelden"),
    path("a/<str:code>/", views_warten.code, name="code"),
]
