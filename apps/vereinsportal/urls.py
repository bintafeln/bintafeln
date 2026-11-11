from django.urls import path

from apps.vereinsportal import views

app_name = "vereinsportal"

urlpatterns = [
    path("", views.start, name="start"),
    path("export/", views.export, name="export"),
    path("beleg/<int:pk>/", views.beleg, name="beleg"),
    path("abruf/", views.abruf, name="abruf"),
    path("abruf/stand/", views.abruf_stand, name="abruf_stand"),
    path("dankesbriefe/", views.briefe, name="briefe"),
    path("sammelbescheinigungen/", views.sammel, name="sammel"),
    path("sammelbescheinigungen/<int:pk>/", views.sammel_datei, name="sammel_datei"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
