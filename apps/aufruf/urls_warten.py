"""Wartezeit aufs Handy (ADR 0090): öffentlich, ohne Anmeldung bei bintafeln."""

from django.urls import path

from apps.aufruf import views_warten

app_name = "warten"

urlpatterns = [
    path("", views_warten.seite, name="seite"),
    path("abmelden/", views_warten.abmelden, name="abmelden"),
    path("push/an/", views_warten.push_an, name="push_an"),
    path("push/aus/", views_warten.push_aus, name="push_aus"),
    path("sw.js", views_warten.service_worker, name="sw"),
    path("manifest.json", views_warten.manifest, name="manifest"),
    path("a/<str:code>/", views_warten.code, name="code"),
]
