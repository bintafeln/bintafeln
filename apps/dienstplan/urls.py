from django.urls import path

from apps.dienstplan import views

app_name = "dienstplan"

urlpatterns = [
    path("", views.uebersicht, name="plan"),
    path("pdf/", views.plan_pdf, name="pdf"),
    path("platz/<str:datum>/<int:aufgabe>/", views.platz, name="platz"),
    path("meine/", views.meine, name="meine"),
    path("ausfall/", views.ausfall, name="ausfall"),
    path("ausfall/<int:pk>/loeschen/", views.ausfall_loeschen, name="ausfall_loeschen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("stelle/<int:pk>/", views.stelle, name="stelle"),
    path("aufgabe/<int:pk>/", views.aufgabe, name="aufgabe"),
    path("aufgabe/<int:pk>/loeschen/", views.aufgabe_loeschen, name="aufgabe_loeschen"),
    path("helfer/neu/", views.helfer, name="helfer_neu"),
    path("helfer/<int:pk>/", views.helfer, name="helfer"),
    path("helfer/<int:pk>/loeschen/", views.helfer_loeschen, name="helfer_loeschen"),
    path("helfer/uebernehmen/", views.helfer_uebernehmen, name="helfer_uebernehmen"),
    path("telegram/", views.telegram_pruefen, name="telegram"),
    path("beispiel/", views.beispiel, name="beispiel"),
]
