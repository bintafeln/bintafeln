from django.urls import path

from apps.touren import views, views_touren

app_name = "touren"

urlpatterns = [
    path("", views_touren.heute, name="heute"),
    path("tour/<int:pk>/", views_touren.fahren, name="fahren"),
    path("planen/", views_touren.touren, name="touren"),
    path("planen/neu/", views_touren.tour_neu, name="tour_neu"),
    path("planen/importieren/", views_touren.touren_importieren, name="touren_importieren"),
    path("planen/<int:pk>/", views_touren.tour, name="tour"),
    path("planen/<int:pk>/loeschen/", views_touren.tour_loeschen, name="tour_loeschen"),
    path("planen/<int:pk>/senden/", views_touren.tour_senden, name="tour_senden"),
    path("planen/<int:pk>/halt/", views_touren.halt_neu, name="halt_neu"),
    path("planen/halt/<int:pk>/", views_touren.halt_aendern, name="halt_aendern"),
    path("stationen/", views.stationen, name="stationen"),
    path("stationen/neu/", views.bearbeiten, name="neu"),
    path("stationen/importieren/", views.importieren_ansicht, name="importieren"),
    path("stationen/ins-adressbuch/", views.alle_uebertragen, name="alle_uebertragen"),
    path("stationen/<int:pk>/", views.station, name="station"),
    path("stationen/<int:pk>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("stationen/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("stationen/<int:pk>/ins-adressbuch/", views.uebertragen, name="uebertragen"),
]
