from django.urls import path

from apps.fahrdienst import views

app_name = "fahrdienst"

urlpatterns = [
    path("", views.uebersicht, name="plan"),
    path("pdf/", views.plan_pdf, name="pdf"),
    path("telegram/", views.telegram_pruefen, name="telegram"),
    path("platz/<str:datum>/<int:tour>/<int:nr>/", views.platz, name="platz"),
    path("meine/", views.meine, name="meine"),
    path("ausfall/", views.ausfall, name="ausfall"),
    path("ausfall/<int:pk>/loeschen/", views.ausfall_loeschen, name="ausfall_loeschen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("tour/neu/", views.tour, name="tour_neu"),
    path("tour/<int:pk>/", views.tour, name="tour"),
    path("tour/<int:pk>/loeschen/", views.tour_loeschen, name="tour_loeschen"),
    path("tour/<int:pk>/besetzung/", views.besetzung, name="besetzung"),
    path("springer/neu/", views.springer, name="springer_neu"),
    path("springer/<int:pk>/", views.springer, name="springer"),
    path("springer/<int:pk>/loeschen/", views.springer_loeschen, name="springer_loeschen"),
]
