from django.urls import path

from apps.listen import views

app_name = "listen"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("eigene/<int:pk>/", views.eigene, name="eigene"),
    path("eigene/<int:pk>/loeschen/", views.eigene_loeschen, name="eigene_loeschen"),
    path("<str:kennung>/", views.liste, name="liste"),
    path("<str:kennung>/export/<str:art>/", views.export, name="export"),
    path("<str:kennung>/speichern/", views.speichern, name="speichern"),
]
