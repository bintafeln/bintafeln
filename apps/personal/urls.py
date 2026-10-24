from django.urls import path

from apps.personal import views, views_arbeitszeit

app_name = "personal"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("arbeitszeit/", views_arbeitszeit.meine, name="meine_arbeitszeit"),
    path("arbeitszeit/stempeln/", views_arbeitszeit.stempeln, name="stempeln"),
    path(
        "arbeitszeit/einstellungen/",
        views_arbeitszeit.einstellungen,
        name="arbeitszeit_einstellungen",
    ),
    path("<int:pk>/zeiten/", views_arbeitszeit.zeiten, name="zeiten"),
    path("<int:pk>/zeiten/neu/", views_arbeitszeit.zeit_bearbeiten, name="zeit_neu"),
    path("<int:pk>/zeiten/<int:buchung>/", views_arbeitszeit.zeit_bearbeiten, name="zeit"),
    path(
        "<int:pk>/zeiten/<int:buchung>/loeschen/",
        views_arbeitszeit.zeit_loeschen,
        name="zeit_loeschen",
    ),
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
