from django.urls import path

from apps.wochenuebersicht import views

app_name = "wochenuebersicht"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("pdf/<str:art>/", views.als_pdf, name="pdf"),
    path("selbstabholer/", views.selbstabholer, name="selbstabholer"),
    path("selbstabholer/neu/", views.selbstabholer_bearbeiten, name="selbstabholer_neu"),
    path(
        "selbstabholer/<int:pk>/", views.selbstabholer_bearbeiten, name="selbstabholer_bearbeiten"
    ),
    path(
        "selbstabholer/<int:pk>/loeschen/",
        views.selbstabholer_loeschen,
        name="selbstabholer_loeschen",
    ),
    path("selbstabholer/<int:pk>/notiz/", views.selbstabholer_notiz, name="selbstabholer_notiz"),
    path(
        "selbstabholer/notiz/<int:pk>/loeschen/",
        views.selbstabholer_notiz_loeschen,
        name="selbstabholer_notiz_loeschen",
    ),
    path("reihenfolge/", views.reihenfolge, name="reihenfolge"),
]
