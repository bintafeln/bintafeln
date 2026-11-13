from django.urls import path

from apps.spenden import views

app_name = "spenden"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("entwicklung/", views.entwicklung, name="entwicklung"),
    path("spalten/", views.spalten, name="spalten"),
    path("neu/", views.bearbeiten, name="neu"),
    path("import/", views.importieren_ansicht, name="importieren"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("bestaetigungen/", views.bestaetigungen, name="bestaetigungen"),
    path("bestaetigungen/ausstellen/", views.ausstellen, name="ausstellen"),
    path("bestaetigungen/pdf/", views.pdf, name="pdf"),
    path("bestaetigungen/<int:nummer>/stornieren/", views.stornieren, name="stornieren"),
    path(
        "bestaetigungen/<int:nummer>/unterschreiben/",
        views.neu_unterschreiben,
        name="neu_unterschreiben",
    ),
    path("bestaetigungen/unterschrift/", views.unterschrift, name="unterschrift"),
    path("bestaetigungen/unterschrift/bild/", views.unterschrift_bild, name="unterschrift_bild"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("dankesbriefe/", views.dank, name="dank"),
    path("belege/", views.belege, name="belege"),
    path("belege/<int:pk>/", views.beleg, name="beleg"),
]
