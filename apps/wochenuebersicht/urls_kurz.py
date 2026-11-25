"""Kurze Adresse einer eigenen Liste der Wochenübersicht: ``/liste/<kurz>/`` (mit Anmeldung)."""

from django.urls import path

from apps.wochenuebersicht import views

app_name = "wochenliste"

urlpatterns = [path("<slug:kurz>/", views.eigene_pdf, name="liste")]
