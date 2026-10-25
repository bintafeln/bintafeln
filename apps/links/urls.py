from django.urls import path

from apps.links import views

app_name = "links"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.link, name="link_neu"),
    path("<int:pk>/", views.link, name="link"),
    path("gruppen/neu/", views.gruppe, name="gruppe_neu"),
    path("gruppen/<int:pk>/", views.gruppe, name="gruppe"),
    path("<str:art>/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
