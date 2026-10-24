from django.urls import path

from apps.personal import views

app_name = "personal"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("<int:pk>/", views.person, name="person"),
    path("<int:pk>/vertrag/", views.vertrag_neu, name="vertrag_neu"),
    path("<int:pk>/vertrag/<int:vertrag>/", views.vertrag_bearbeiten, name="vertrag"),
    path(
        "<int:pk>/vertrag/<int:vertrag>/loeschen/", views.vertrag_loeschen, name="vertrag_loeschen"
    ),
    path(
        "<int:pk>/vertrag/<int:vertrag>/dokument/",
        views.dokument_ansehen,
        name="dokument_ansehen",
    ),
    path(
        "<int:pk>/vertrag/<int:vertrag>/dokument/hochladen/",
        views.dokument_hochladen,
        name="dokument_hochladen",
    ),
    path(
        "<int:pk>/vertrag/<int:vertrag>/dokument/loeschen/",
        views.dokument_loeschen,
        name="dokument_loeschen",
    ),
    path("<int:pk>/abwesenheit/", views.abwesenheit_neu, name="abwesenheit_neu"),
    path("<int:pk>/urlaubsjahr/", views.urlaubsjahr, name="urlaubsjahr"),
    path("<int:pk>/stunden/", views.stunden_neu, name="stunden_neu"),
    path("<int:pk>/<str:art>/<int:eintrag>/loeschen/", views.eintrag_loeschen, name="loeschen"),
]
