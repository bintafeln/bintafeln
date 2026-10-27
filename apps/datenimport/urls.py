from django.urls import path

from apps.datenimport import views

app_name = "datenimport"

urlpatterns = [
    path("", views.start, name="start"),
    path("<uuid:pk>/", views.zuordnen, name="zuordnen"),
    path("<uuid:pk>/abgleich/", views.abgleich_ansehen, name="abgleich"),
    path("<uuid:pk>/verwerfen/", views.verwerfen, name="verwerfen"),
    path("vorlage/<int:pk>/loeschen/", views.vorlage_loeschen, name="vorlage_loeschen"),
]
