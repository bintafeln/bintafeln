from django.urls import path

from apps.kunden import views

app_name = "kunden"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("haushalt/<path:kundennummer>/auskunft/", views.auskunft, name="auskunft"),
    path("haushalt/<path:kundennummer>/ausweis/", views.ausweis, name="ausweis"),
    path("haushalt/<path:kundennummer>/", views.haushalt, name="haushalt"),
    path("zugriffe/", views.zugriffe, name="zugriffe"),
    path("import/", views.import_hochladen, name="import"),
    path("import/<uuid:pk>/", views.import_vorschau, name="import_vorschau"),
    path("import/<uuid:pk>/uebernehmen/", views.import_uebernehmen, name="import_uebernehmen"),
    path("import/<uuid:pk>/verwerfen/", views.import_verwerfen, name="import_verwerfen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("zusatzfelder/neu/", views.zusatzfeld_bearbeiten, name="zusatzfeld_neu"),
    path("zusatzfelder/<int:pk>/", views.zusatzfeld_bearbeiten, name="zusatzfeld"),
]
