from django.urls import path

from apps.abrechnung import views

app_name = "abrechnung"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("stelle/<int:stelle>/<str:monat>/", views.monat, name="monat"),
    path("<int:pk>/pdf/", views.als_pdf, name="pdf"),
    path("<int:pk>/<str:was>/", views.aktion, name="aktion"),
    path("ausgabe/<int:pk>/quittung/", views.quittung, name="quittung"),
    path("ausgabe/<int:pk>/loeschen/", views.posten_loeschen, name="posten_loeschen"),
    path("quittungen/<str:monat>/", views.quittungen, name="quittungen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
]
